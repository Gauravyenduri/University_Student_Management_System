from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
import logging

logger = logging.getLogger(__name__)

import json # Ensure json is imported

# --- Existing Exam Functions (Modify if needed) ---
def get_exams_for_course(db: Session, course_id: int) -> List[models.Exam]:
    # Eager load questions if always needed on list view
    return db.query(models.Exam).filter(models.Exam.course_id == course_id)\
        .options(joinedload(models.Exam.mcq_questions))\
        .order_by(models.Exam.date.desc(), models.Exam.name).all()

def get_exam_by_id_with_questions(db: Session, exam_id: int) -> Optional[models.Exam]:
    """Retrieves exam and eagerly loads its MCQ questions."""
    logger.debug(f"Fetching exam ID {exam_id} with MCQ questions.")
    exam = db.query(models.Exam).options(
        selectinload(models.Exam.mcq_questions) # Eagerly load questions
    ).filter(models.Exam.id == exam_id).first()
    if exam:
        logger.debug(f"Found exam '{exam.name}' with {len(exam.mcq_questions)} questions.")
    else:
        logger.warning(f"Exam ID {exam_id} not found when fetching with questions.")
    return exam


# create_exam: Might set total_marks to 0 initially, updated later based on questions
def create_exam(db: Session, course_id: int, name: str, exam_type: models.ExamType,
                exam_date: Optional[date], description: Optional[str]) -> models.Exam:
    # ... (checks for course, duplicate name) ...
    db_exam = models.Exam(
        course_id=course_id, name=name, date=exam_date, type=exam_type,
        total_marks=0.0, # Start with 0 marks
        description=description, is_published=False # Default unpublished
    )
    # ... (commit logic) ...
    db.add(db_exam); #...commit/refresh/error handling
    db.commit()
    db.refresh(db_exam)
    return db_exam

# update_exam: Might recalculate total_marks based on MCQs
def update_exam_details(db: Session, exam_id: int, update_data: Dict[str, Any]) -> Optional[models.Exam]:
    """Updates Exam details (name, type, date etc) but NOT questions/marks here."""
    db_exam = db.query(models.Exam).filter(models.Exam.id == exam_id).first() # Don't need questions here
    if not db_exam: return None
    updated = False
    # ... (update name, date, type, description, is_published as needed from update_data) ...
    if 'name' in update_data and update_data['name'] != db_exam.name: db_exam.name = update_data['name']; updated = True # Add unique check if needed
    if 'date' in update_data and update_data['date'] != db_exam.date: db_exam.date = update_data['date']; updated = True
    if 'type' in update_data and update_data['type'] != db_exam.type: db_exam.type = update_data['type']; updated = True # Assume already enum
    if 'description' in update_data and update_data['description'] != db_exam.description: db_exam.description = update_data['description']; updated = True
    if 'is_published' in update_data and update_data['is_published'] != db_exam.is_published: db_exam.is_published = update_data['is_published']; updated = True

    if not updated: return db_exam
    try: db.add(db_exam); db.commit(); db.refresh(db_exam); return db_exam
    except Exception as e: db.rollback(); logger.error(...); raise ValueError("DB error updating exam details.")


# delete_exam: Now also deletes related MCQs due to cascade. Check results dependency remains.
def delete_exam(db: Session, exam_id: int) -> bool:
     # ... (check for results as before) ...
     # Cascade delete should handle MCQ questions if relationship is set correctly
     db_exam = get_exam_by_id_with_questions(db, exam_id) # Use simple get here
     if not db_exam: return False
     # Check results...
     if db.query(models.Result.id).filter(models.Result.exam_id == exam_id).first():
          raise ValueError(f"Cannot delete exam '{db_exam.name}' with existing results.")
     try: db.delete(db_exam); db.commit(); return True
     except Exception as e: db.rollback(); logger.error(...); raise ValueError("DB error deleting exam.")


# --- NEW MCQ Question Service Functions ---

def save_mcq_questions_for_exam(db: Session, exam_id: int, questions_data: List[Dict[str, Any]]) -> Tuple[int, float]:
    """
    Adds/Updates/Deletes MCQ questions for a specific exam.
    questions_data format: [{'id': str_or_none ('5', 'new_1', ''), 'question_text': str, 'marks': str, 'options': [{'text': str, 'is_correct': bool}, ...], 'delete': bool}, ...]
    Returns: (number of questions saved/updated, total marks)
    """
    exam = get_exam_by_id_with_questions(db, exam_id) # Use eager loading function
    if not exam: raise ValueError(f"Exam with ID {exam_id} not found.")
    logger.info(f"Service: Saving MCQs for exam ID {exam_id}. Received {len(questions_data)} question entries.")

    existing_mcqs_map = {mcq.id: mcq for mcq in exam.mcq_questions}
    processed_mcq_ids = set() # Keep track of DB IDs processed from the input
    total_marks = 0.0
    saved_count = 0

    for q_data in questions_data:
        mcq_id_str = q_data.get('id') # String ID from form ('5', 'new_1', None, '')
        mcq_id_db = None # The actual integer ID if it exists in DB
        is_new_question_from_form = True # Assume new unless we find a matching numeric ID

        # --- Determine if it's an existing question based on ID ---
        if mcq_id_str and mcq_id_str.isdigit():
            try:
                mcq_id_db = int(mcq_id_str)
                if mcq_id_db in existing_mcqs_map:
                    is_new_question_from_form = False # It's an existing question
                    processed_mcq_ids.add(mcq_id_db) # Mark DB ID as processed
                else:
                    # ID is numeric but doesn't match existing IDs for THIS exam - potentially an error or stale data
                    logger.warning(f"Received existing numeric ID {mcq_id_db} for exam {exam_id}, but it wasn't found in current questions. Skipping.")
                    continue # Skip this entry
            except ValueError:
                logger.warning(f"Invalid numeric ID '{mcq_id_str}' treated as new question attempt.")
                is_new_question_from_form = True
                mcq_id_db = None # Reset just in case
        elif mcq_id_str and mcq_id_str.startswith("new_"):
             is_new_question_from_form = True # Explicitly new
             mcq_id_db = None
        else: # No ID or non-numeric/non-'new_' string
            is_new_question_from_form = True
            mcq_id_db = None

        question_text = q_data.get('question_text', '').strip()
        marks_str = q_data.get('marks', '1.0')
        options_list = q_data.get('options', [])
        delete_flag = q_data.get('delete', False)

        # --- Validation ---
        if not question_text and not (delete_flag and not is_new_question_from_form): # Skip empty if not deleting existing
            logger.debug(f"Skipping Q (ID/Str: {mcq_id_str}): No text and not deleting existing.")
            continue
        try: marks = float(marks_str)
        except (ValueError, TypeError): marks = 1.0
        if marks <= 0: marks = 1.0
        if not delete_flag: # Validations only needed if not deleting
             if not isinstance(options_list, list) or len(options_list) < 2:
                 logger.warning(f"Skipping Q '{question_text[:30]}...' (ID/Str: {mcq_id_str}): < 2 options."); continue
             has_correct_option = any(opt.get('is_correct') for opt in options_list if isinstance(opt, dict))
             if not has_correct_option:
                 logger.warning(f"Skipping Q '{question_text[:30]}...' (ID/Str: {mcq_id_str}): No correct option."); continue
        try: options_json = json.dumps(options_list)
        except TypeError: logger.warning(f"Skipping Q '{question_text[:30]}...' (ID/Str: {mcq_id_str}): Invalid options format."); continue


        # --- DB Operation ---
        if not is_new_question_from_form and mcq_id_db is not None:
            # Potential UPDATE or DELETE
            mcq_to_process = existing_mcqs_map.get(mcq_id_db)
            if not mcq_to_process: # Should have been caught earlier, but double check
                logger.error(f"Consistency Error: MCQ {mcq_id_db} not found in map for update/delete.")
                continue

            if delete_flag:
                logger.info(f"Service: Deleting existing MCQ {mcq_id_db} for exam {exam_id}")
                db.delete(mcq_to_process)
                # Do NOT add marks or increment saved_count
            else:
                # Update existing MCQ
                logger.debug(f"Service: Updating existing MCQ {mcq_id_db} for exam {exam_id}")
                mcq_to_process.question_text = question_text
                mcq_to_process.marks = marks
                mcq_to_process.options = options_json
                db.add(mcq_to_process) # Add to session for update
                total_marks += marks
                saved_count += 1

        elif is_new_question_from_form and not delete_flag:
            # Add NEW question
            logger.debug(f"Service: Adding new MCQ '{question_text[:30]}...' for exam {exam_id}")
            new_mcq = models.MCQQuestion(
                exam_id=exam_id, question_text=question_text,
                marks=marks, options=options_json
            )
            db.add(new_mcq)
            total_marks += marks
            saved_count += 1
        # else: # Case: delete_flag=True and is_new=True - do nothing

    # --- Delete questions that were in DB but not processed from form ---
    ids_in_db = set(existing_mcqs_map.keys())
    ids_to_delete = ids_in_db - processed_mcq_ids
    if ids_to_delete:
        logger.info(f"Service: Deleting {len(ids_to_delete)} MCQs ({ids_to_delete}) not in submission for exam {exam_id}")
        db.query(models.MCQQuestion).filter(
            models.MCQQuestion.exam_id == exam_id,
            models.MCQQuestion.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)

    # --- Update Exam Total Marks ---
    rounded_total_marks = round(total_marks, 2)
    if exam.total_marks != rounded_total_marks:
        logger.info(f"Service: Updating total marks for exam {exam_id} from {exam.total_marks or 0.0} to {rounded_total_marks}")
        exam.total_marks = rounded_total_marks
        db.add(exam)

    # --- Commit ---
    try:
        db.commit()
        logger.info(f"Service: Successfully saved MCQs for exam {exam_id}. Saved/Updated: {saved_count}. Final Total Marks: {rounded_total_marks}")
        return saved_count, rounded_total_marks
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing MCQ save for exam {exam_id}: {e}", exc_info=True)
        raise ValueError("Database error saving MCQ questions.")


# app/services/exam_service.py
def get_published_exams_for_student_courses(db: Session, student_id: int) -> List[models.Exam]:
    """
    Retrieves published exams for all courses a given student is currently enrolled in.
    Includes MySQL-compatible NULLS LAST ordering for date.
    """
    logger.debug(f"SERVICE: Fetching published exams for student {student_id}")
    try:
        # Subquery to get course IDs the student is enrolled in
        enrolled_course_ids_query = db.query(models.Enrollment.course_id).filter(
            models.Enrollment.student_id == student_id
        ).distinct()

        enrolled_ids = [id_tuple[0] for id_tuple in enrolled_course_ids_query.all()]
        logger.debug(f"SERVICE: Student {student_id} enrolled in course IDs: {enrolled_ids}")

        if not enrolled_ids:
             logger.debug(f"SERVICE: Student {student_id} not enrolled in any courses.")
             return []
        from sqlalchemy import case, desc
        # Query exams linked to those course IDs AND published
        query = db.query(models.Exam).options(
            joinedload(models.Exam.course) # Load course name
        ).join(
            models.Course, models.Exam.course_id == models.Course.id # Explicit join for ordering
        ).filter(
            models.Exam.course_id.in_(enrolled_ids),
            models.Exam.is_published == True
        ).order_by(
            # --- MySQL Compatible NULLS LAST ---
            # Order by whether the date is NULL first (NULLs come last -> 1)
            case((models.Exam.date.is_(None), 1), else_=0),
            # Then order by the date descending for non-null dates
            desc(models.Exam.date),
            # --- End MySQL Compatibility ---
            models.Course.name, # Then by course name
            models.Exam.name    # Then by exam name
        )

        published_exams = query.all()
        logger.debug(f"SERVICE: Found {len(published_exams)} published exams for student {student_id}")
        return published_exams
    except Exception as e:
        logger.error(f"SERVICE: Exception fetching published exams for student {student_id}: {e}", exc_info=True)
        raise e # Re-raise

# Optional: Function to get details of a specific published exam if student clicks on it
def get_published_exam_details_for_student(db: Session, exam_id: int, student_id: int) -> Optional[models.Exam]:
    """
    Retrieves details of a specific published exam, ensuring the student is enrolled in the course.
    (Does not load questions here - separate process for taking exam)
    """
    exam = db.query(models.Exam).options(joinedload(models.Exam.course))\
        .filter(models.Exam.id == exam_id, models.Exam.is_published == True)\
        .first()

    if not exam:
        return None # Exam not found or not published

    # Verify student is enrolled in this exam's course
    is_enrolled = db.query(models.Enrollment.id).filter(
        models.Enrollment.student_id == student_id,
        models.Enrollment.course_id == exam.course_id
    ).first()

    if not is_enrolled:
        logger.warning(f"Student {student_id} attempted to access unpublished/unauthorized exam {exam_id}")
        return None # Student not enrolled in this course

    return exam

def get_exam_questions_for_student(db: Session, exam_id: int) -> List[Dict]:
    """
    Retrieves MCQ questions for an exam, preparing them for student attempt.
    Crucially, it parses options but does NOT include the 'is_correct' flag.
    Option order should be preserved if possible or randomized consistently.
    """
    logger.debug(f"SERVICE: Fetching questions for student attempt, exam ID {exam_id}")
    questions = db.query(models.MCQQuestion).filter(
        models.MCQQuestion.exam_id == exam_id
    ).order_by(models.MCQQuestion.id).all() # Consistent order is important

    output = []
    for mcq in questions:
        options_for_student = []
        try:
            options_list = json.loads(mcq.options or '[]')
            # Only include the text, shuffle order maybe? For now, keep order.
            options_for_student = [{"text": opt.get("text")} for opt in options_list if isinstance(opt, dict) and opt.get("text")]
        except json.JSONDecodeError:
            logger.warning(f"Could not parse options for MCQ {mcq.id} during student fetch.")

        output.append({
            "id": mcq.id,
            "question_text": mcq.question_text,
            "marks": mcq.marks,
            "options": options_for_student # List of dicts containing only 'text'
        })
    logger.debug(f"SERVICE: Prepared {len(output)} questions for student attempt.")
    return output

def check_exam_attempt_exists(db: Session, exam_id: int, student_id: int) -> bool:
    """Checks if a result record (attempt) exists for the student and exam."""
    # Check if a Result record exists and potentially if it's submitted
    existing_result = db.query(models.Result.id).filter(
        models.Result.exam_id == exam_id,
        models.Result.student_id == student_id
        # Optionally add filter(models.Result.submitted_at.isnot(None)) to only count submitted attempts
    ).first()
    logger.debug(f"SERVICE: Attempt check for Student {student_id}, Exam {exam_id}. Found: {existing_result is not None}")
    return existing_result is not None
