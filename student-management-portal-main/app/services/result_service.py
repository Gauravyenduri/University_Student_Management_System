# app/services/result_service.py (New File)
from sqlalchemy.orm import Session, joinedload, selectinload
from app import models
from typing import List, Optional, Dict, Any
from datetime import datetime, date # Need datetime now
import logging
import json

logger = logging.getLogger(__name__)

def get_result_by_exam_and_student(db: Session, exam_id: int, student_id: int) -> Optional[models.Result]:
    """Gets the result record for a specific student and exam."""
    return db.query(models.Result).filter(
        models.Result.exam_id == exam_id,
        models.Result.student_id == student_id
    ).first()

def record_exam_submission(
    db: Session,
    exam_id: int,
    student_id: int,
    submitted_answers: Dict[int, str] # {mcq_question_id: selected_option_text}
) -> models.Result:
    """
    Records student's answers, calculates score, and saves the result.
    Returns the saved/updated Result object.
    """
    logger.info(f"Recording submission for Student {student_id}, Exam {exam_id}")

    # 1. Find or Create Result Record
    result = get_result_by_exam_and_student(db, exam_id, student_id)
    if result and result.submitted_at:
        raise ValueError("Exam has already been submitted.") # Prevent re-submission
    elif not result:
        logger.debug("Creating new Result record.")
        result = models.Result(exam_id=exam_id, student_id=student_id)
        db.add(result)
        db.flush() # Get result.id if needed for answers immediately
    else:
         logger.debug(f"Found existing Result record ID: {result.id}. Updating answers.")
         # Clear previous answers if re-submitting an incomplete attempt? Assume we overwrite.
         db.query(models.MCQAnswer).filter(models.MCQAnswer.result_id == result.id).delete()
         db.flush() # Apply deletion before adding new


    # 2. Fetch Exam Questions with Correct Answers (for grading)
    exam = db.query(models.Exam).options(
        selectinload(models.Exam.mcq_questions) # Need questions + options
    ).filter(models.Exam.id == exam_id).first()
    if not exam: raise ValueError("Exam not found during submission.")
    if not exam.is_published: raise ValueError("Cannot submit to an unpublished exam.")

    # Create a map of question ID to its data (including parsed correct option text)
    correct_answers_map = {}
    total_possible_marks = 0.0
    for mcq in exam.mcq_questions:
        total_possible_marks += mcq.marks
        correct_text = None
        try:
            options_list = json.loads(mcq.options or '[]')
            correct_opt = next((opt for opt in options_list if isinstance(opt, dict) and opt.get('is_correct') == True), None)
            if correct_opt: correct_text = correct_opt.get('text')
        except json.JSONDecodeError: pass # Ignore parsing errors here, focus on grading
        correct_answers_map[mcq.id] = {"correct_text": correct_text, "marks": mcq.marks}


    # 3. Process Submitted Answers and Calculate Score
    student_score = 0.0
    mcq_answers_to_save = []

    for question_id_str, selected_option_text in submitted_answers.items():
        try: question_id = int(question_id_str)
        except ValueError: logger.warning(f"Invalid question ID format '{question_id_str}' in submission."); continue

        question_info = correct_answers_map.get(question_id)
        is_correct = False
        if question_info:
            # Compare submitted text with the stored correct option text
            if question_info["correct_text"] is not None and selected_option_text == question_info["correct_text"]:
                is_correct = True
                student_score += question_info["marks"]

        # Create MCQAnswer object
        answer = models.MCQAnswer(
            result_id=result.id,
            mcq_question_id=question_id,
            selected_option_text=selected_option_text,
            is_correct=is_correct
        )
        mcq_answers_to_save.append(answer)

    # Add all answers to session
    db.add_all(mcq_answers_to_save)

    # 4. Update Result Record
    result.score = round(student_score, 2)
    result.submitted_at = datetime.utcnow()
    result.is_graded = True # Auto-graded for MCQs
    # Optionally calculate letter grade based on score/total_marks percentage
    # result.grade = calculate_grade(result.score, total_possible_marks)

    # 5. Update Exam Total Marks (if it wasn't set correctly before)
    # This ensures the Result percentage calculation is accurate later
    if exam.total_marks != total_possible_marks:
         logger.warning(f"Exam {exam_id} total marks mismatch. DB: {exam.total_marks}, Calculated: {total_possible_marks}. Updating exam.")
         exam.total_marks = round(total_possible_marks, 2)
         db.add(exam)

    # 6. Commit
    try:
        db.commit()
        db.refresh(result) # Refresh to get final state
        logger.info(f"Submission recorded for Student {student_id}, Exam {exam_id}. Score: {result.score}/{total_possible_marks}")
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing exam submission for Student {student_id}, Exam {exam_id}: {e}", exc_info=True)
        raise ValueError("Database error saving exam submission.")

def get_result_details_with_answers(db: Session, result_id: int, student_id: int) -> Optional[models.Result]:
    """
    Retrieves a specific result, ensuring it belongs to the student,
    and loads related exam, questions, and student answers.
    Parses correct answers for comparison.
    """
    logger.debug(f"Fetching result details for Result ID: {result_id}, Student ID: {student_id}")
    result = db.query(models.Result).options(
        joinedload(models.Result.student), # Load student info (optional)
        joinedload(models.Result.exam).options( # Load exam...
            selectinload(models.Exam.mcq_questions) # ...and its questions
        ),
        selectinload(models.Result.mcq_answers) # Load student's answers for this result
    ).filter(
        models.Result.id == result_id,
        models.Result.student_id == student_id # Crucial ownership check
    ).first()

    if not result:
        logger.warning(f"Result ID {result_id} not found for student {student_id}.")
        return None
    if not result.exam: # Should not happen with joinload, but safety check
        logger.error(f"Exam details missing for Result ID {result_id}.")
        return None # Or raise an error

    # --- Process questions and answers for easy template use ---
    # Create maps for quick lookups
    student_answers_map = {ans.mcq_question_id: ans.selected_option_text for ans in result.mcq_answers}
    questions_details = []

    for mcq in result.exam.mcq_questions:
        question_data = {
            "id": mcq.id,
            "question_text": mcq.question_text,
            "marks": mcq.marks,
            "options": [], # Will contain {'text': str, 'is_correct': bool, 'was_selected': bool}
            "student_answer_text": student_answers_map.get(mcq.id),
            "is_student_correct": None # Will be True/False
        }
        correct_option_text = None
        try:
            options_list = json.loads(mcq.options or '[]')
            student_selected_text = question_data["student_answer_text"]

            for option in options_list:
                if isinstance(option, dict) and 'text' in option:
                    text = option.get('text')
                    is_correct = option.get('is_correct', False)
                    was_selected = (text == student_selected_text)

                    question_data["options"].append({
                        "text": text,
                        "is_correct": is_correct,
                        "was_selected": was_selected
                    })
                    if is_correct:
                        correct_option_text = text # Store the text of the correct option

        except json.JSONDecodeError:
             logger.warning(f"Could not parse options for MCQ {mcq.id} during result view.")

        # Determine if the student's answer was correct
        question_data["is_student_correct"] = (correct_option_text is not None and student_selected_text == correct_option_text)
        questions_details.append(question_data)

    # Attach the processed questions list to the result object (not saved to DB)
    result.processed_questions = questions_details
    # --- End Processing ---

    logger.debug(f"Successfully prepared result details for Result ID: {result_id}")
    return result