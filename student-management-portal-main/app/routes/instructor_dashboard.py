# app/routes/instructor_dashboard.py

from fastapi import (
    APIRouter, Depends, Request, Form, HTTPException, status, Query, Response,
    Body # Import Body if needed for JSON posts later
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
import logging
from datetime import date, datetime
from typing import Optional, List, Dict
import urllib.parse
import json

# Local imports
from app import database, models
from app.services import (
    auth_service, schedule_service, attendance_service,
    exam_service, course_service # Need all relevant services
)
from app.models import UserRole, AttendanceStatus, ExamType, Schedule # Import models needed

logger = logging.getLogger(__name__)

# Router for instructor-specific views/actions
router = APIRouter(
)
templates = Jinja2Templates(directory="app/templates")


# === Instructor Dashboard Route ===
@router.get("/dashboard", response_class=HTMLResponse, name="instructor_dashboard")
async def get_instructor_dashboard(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the overview dashboard for the logged-in instructor."""
    logger.info(f"Accessing instructor dashboard for user: {current_user.username}")
    instructor_profile = current_user.instructor_profile
    dashboard_data = {
        "teaching_course_count": 0,
        "upcoming_classes_count": 0, # Placeholder
        "pending_gradings_count": 0 # Placeholder
    }

    if instructor_profile:
        try:
            # Count distinct courses taught (based on schedule)
            dashboard_data["teaching_course_count"] = db.query(func.count(models.Schedule.course_id.distinct()))\
                .filter(models.Schedule.instructor_id == instructor_profile.id).scalar() or 0

            # Fetch upcoming classes (e.g., today or next few days - requires more logic)
            # ...

            # Fetch exams/assignments needing grading (requires Result model logic)
            # ...

        except Exception as e:
            logger.error(f"Error fetching dashboard summary data for instructor {instructor_profile.id}: {e}", exc_info=True)
            toast_error = "Could not load all dashboard summary data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request, "user": current_user, "instructor_profile": instructor_profile,
        "UserRole": UserRole, "page_title": "Instructor Dashboard",
        "dashboard_data": dashboard_data,
        "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("instructor/instructor_dashboard.html", context)


# === Attendance Management Routes ===

# GET: Show attendance form/list
@router.get("/attendance", response_class=HTMLResponse, name="instructor_attendance_form")
async def show_attendance_form(
    request: Request, response: Response, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
    course_id: Optional[int] = Query(None), # Changed back to course_id
    attendance_date_str: Optional[str] = Query(None),
    toast_error: Optional[str] = Query(None), toast_success: Optional[str] = Query(None)
):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(404, "Instructor profile not found.")

    # Fetch distinct courses taught by this instructor
    teaching_schedules = db.query(models.Schedule).options(joinedload(models.Schedule.course))\
        .filter(models.Schedule.instructor_id == instructor_profile.id).distinct(models.Schedule.course_id).all()
    teaching_courses = sorted([s.course for s in teaching_schedules if s.course], key=lambda c: c.name)

    selected_course: Optional[models.Course] = None
    selected_date: Optional[date] = None
    students_for_schedule: List[models.Student] = []
    attendance_status_map: Dict[int, models.AttendanceStatus] = {}
    found_schedule_id: Optional[int] = None # Store the schedule ID found for the course/day

    # Validate selected course_id
    if course_id:
        selected_course = next((c for c in teaching_courses if c.id == course_id), None)
        if not selected_course:
            toast_error = "Permission denied for selected course."; course_id = None # Reset if invalid

    # Process date and find schedule if course is valid
    if course_id and selected_course:
        today = date.today()
        if attendance_date_str:
            try:
                selected_date = date.fromisoformat(attendance_date_str)
                if selected_date > today:
                    selected_date = today
                    toast_error = "Cannot select a future date. Showing today's date."
            except ValueError:
                selected_date = today
                toast_error = "Invalid date format. Showing today's date."
        else:
            selected_date = today

        # Determine day of week (0=Monday, 6=Sunday) -> Convert to string name
        day_name = selected_date.strftime('%A') # e.g., "Monday"

        # Find the schedule for this instructor, course, and day
        schedules_on_day = db.query(models.Schedule).filter(
            models.Schedule.instructor_id == instructor_profile.id,
            models.Schedule.course_id == course_id,
            models.Schedule.day_of_week == day_name
        ).order_by(models.Schedule.start_time).all() # Order by time just in case

        if not schedules_on_day:
            toast_error = f"No schedule found for {selected_course.name} on {day_name}s."
        else:
            if len(schedules_on_day) > 1:
                logger.warning(f"Multiple schedules found for instructor {instructor_profile.id}, course {course_id} on {day_name}. Using the first one (ID: {schedules_on_day[0].id}).")
            found_schedule_id = schedules_on_day[0].id # Use the first schedule found

            # Fetch students and attendance using the found schedule_id
            students_for_schedule = attendance_service.get_students_for_schedule(db, found_schedule_id)
            attendance_status_map = attendance_service.get_attendance_records(db, found_schedule_id, selected_date)

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole, "instructor_profile": instructor_profile,
        "teaching_courses": teaching_courses, # Pass courses for dropdown
        "selected_course_id": course_id, # Pass selected course ID
        "selected_date": selected_date,
        "found_schedule_id": found_schedule_id, # Pass the determined schedule ID (or None)
        "students_for_schedule": students_for_schedule, # Pass students for the schedule
        "attendance_status_map": attendance_status_map,
        "attendance_statuses": [status for status in AttendanceStatus], # Pass enum members
        "page_title": "Mark Attendance", "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("instructor/attendance_form.html", context)

# POST: Save attendance data
@router.post("/attendance", response_class=RedirectResponse, name="instructor_save_attendance")
async def save_attendance(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
    course_id: int = Form(...), # Submit course_id from form
    attendance_date_str: str = Form(...)
):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(403, "Instructor profile needed.")
    redirect_url = request.url_for('instructor_attendance_form') # Redirect back to form
    query_params = []
    found_schedule_id: Optional[int] = None

    try:
        attendance_date = date.fromisoformat(attendance_date_str)
        # Keep original selections for redirect
        query_params.append(f"course_id={course_id}")
        query_params.append(f"attendance_date_str={attendance_date_str}")

        # --- Re-determine schedule_id based on submitted course and date ---
        day_name = attendance_date.strftime('%A')
        schedules_on_day = db.query(models.Schedule).filter(
            models.Schedule.instructor_id == instructor_profile.id,
            models.Schedule.course_id == course_id,
            models.Schedule.day_of_week == day_name
        ).all()

        if not schedules_on_day:
            raise ValueError(f"No schedule found for this course on {day_name}s to save attendance against.")
        if len(schedules_on_day) > 1:
             logger.warning(f"Multiple schedules found for instructor {instructor_profile.id}, course {course_id} on {day_name} during save. Using the first one (ID: {schedules_on_day[0].id}).")
        found_schedule_id = schedules_on_day[0].id
        # --- End re-determining schedule_id ---

        # Extract attendance data
        form_data = await request.form()
        attendance_to_save: Dict[int, str] = {}
        for key, value in form_data.items():
            if key.startswith("attendance_status_"):
                try:
                    student_id = int(key.split("_")[-1])
                    status_str = value.strip().upper()
                    if status_str: attendance_to_save[student_id] = status_str
                except (ValueError, IndexError): logger.warning(f"Could not parse attendance key: {key}")

        if not attendance_to_save: raise ValueError("No attendance data submitted.")

        # Call service with the *determined* schedule_id
        created, updated = attendance_service.save_attendance_records(db=db, schedule_id=found_schedule_id, attendance_date=attendance_date, attendance_data=attendance_to_save)
        toast_msg = urllib.parse.quote(f"Attendance saved ({created} created, {updated} updated).")
        query_params.append(f"toast_success={toast_msg}")

    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error saving attendance: {e}")
        query_params.append(f"toast_error={toast_msg}")
    except Exception as e:
        logger.error(f"Unexpected error saving attendance: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        query_params.append(f"toast_error={toast_msg}")

    # Redirect back to the form page with appropriate query params
    final_redirect_url = f"{redirect_url}?{'&'.join(query_params)}"
    return RedirectResponse(final_redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# === Exam Management Routes ===

# GET: List exams for selection or management
@router.get("/exams", response_class=HTMLResponse, name="instructor_manage_exams")
async def manage_exams_page(
    request: Request, response: Response, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
    course_id: Optional[int] = Query(None), toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(404, "Instructor profile not found.")

    # Get courses taught
    instructor_schedules = db.query(models.Schedule).options(joinedload(models.Schedule.course)).filter(models.Schedule.instructor_id == instructor_profile.id).distinct(models.Schedule.course_id).all()
    teaching_courses = sorted([s.course for s in instructor_schedules if s.course], key=lambda c: c.name)

    # Fetch exams based on selected course
    exams_list = []
    selected_course_name = None
    if course_id:
        if course_id not in {c.id for c in teaching_courses}:
             toast_error = "Permission denied for selected course."; course_id = None
        else:
             exams_list = exam_service.get_exams_for_course(db, course_id=course_id)
             selected_course = next((c for c in teaching_courses if c.id == course_id), None)
             if selected_course: selected_course_name = selected_course.name

    # Prepare data for modal dropdowns
    exam_types_json = json.dumps([et.value for et in ExamType])
    courses_json = json.dumps([{"id": c.id, "name": c.name} for c in teaching_courses])

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "teaching_courses": teaching_courses, "selected_course_id": course_id,
        "selected_course_name": selected_course_name, "exams": exams_list,
        "page_title": "Manage Exams", "exam_types_json": exam_types_json,
        "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("instructor/manage_exams.html", context)


# GET: Route for Exam Editor (MCQ Creation)
@router.get("/exams/{exam_id}/edit-mcqs", response_class=HTMLResponse, name="instructor_edit_exam_mcqs")
async def edit_exam_mcqs_page(
    request: Request, exam_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
    toast_error: Optional[str] = Query(None), toast_success: Optional[str] = Query(None)
):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(404, "Instructor profile not found.")

    # Use the service function that fetches questions
    exam = exam_service.get_exam_by_id_with_questions(db, exam_id)
    if not exam: raise HTTPException(404, "Exam not found.")
    # Parse options JSON for template rendering
    questions_with_parsed_options = []
    for mcq in exam.mcq_questions: # exam.mcq_questions should be loaded now
        options_list = []; 
        try: options_list = json.loads(mcq.options or '[]')
        except json.JSONDecodeError: logger.warning(f"Could not parse options JSON for MCQ {mcq.id}")
        questions_with_parsed_options.append({
            "id": mcq.id, "question_text": mcq.question_text,
            "marks": mcq.marks, "options": options_list })
    print(exam)

    context = {
        "request": request, "user": current_user, "UserRole": UserRole, "exam": exam,
        "questions": questions_with_parsed_options, # Pass parsed data
        "page_title": f"Edit MCQs for: {exam.name}", "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("instructor/edit_exam_mcqs.html", context)





# POST: Route to Save MCQs
@router.post("/exams/{exam_id}/save-mcqs", response_class=RedirectResponse, name="instructor_save_exam_mcqs")
async def save_exam_mcqs(
    request: Request,
    exam_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_instructor),
):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(403, "Profile needed.")

    # --- Permission Check ---
    exam = exam_service.get_exam_by_id_with_questions(db, exam_id)
    if not exam: raise HTTPException(404, "Exam not found.")


    # --- Process Dynamic Form Data (REVISED LOGIC) ---
    form_data = await request.form()
    logger.debug(f"--- Received Raw Form Data for Exam {exam_id} ---")
    for key, value in form_data.items(): logger.debug(f"Form Key: '{key}', Value: '{value}'")
    logger.debug(f"--- End Raw Form Data ---")

    questions_to_save = []
    # 1. Identify all unique question indices present in the form
    #    Look for keys like q_text_XXX, q_id_XXX, q_marks_XXX
    q_indices = set()
    for key in form_data:
        if key.startswith('q_text_') or key.startswith('q_id_'):
            # Extract index from keys like 'q_text_new_1' or 'q_id_5'
            index = key.split('_', 2)[-1]  # Get everything after second underscore
            q_indices.add(index)
    logger.debug(f"Identified question indices from form: {q_indices}")

    # 2. Iterate through each identified question index
    for q_index in q_indices:
        # Extract basic question data
        q_id_str = form_data.get(f'q_id_{q_index}') # Existing DB ID (e.g., '5') or '' for new
        q_text = form_data.get(f'q_text_{q_index}', '').strip()
        q_marks_str = form_data.get(f'q_marks_{q_index}', '1.0')
        q_delete = form_data.get(f'q_delete_{q_index}') == 'true'
        # Skip empty questions unless it's an existing one marked for delete
        is_existing_numeric_id = q_id_str and q_id_str.isdigit()
        if not q_text and not (q_delete and is_existing_numeric_id):
            logger.warning(f"Skipping question index {q_index}: No text and not deleting existing.")
            continue

        # Extract options for *this specific* question index
        options_data = []
        # Find all option text inputs for this q_index
        option_text_keys = [k for k in form_data if k.startswith(f'q_{q_index}_opt_text_')]
        # Get the value selected for the 'correct' radio group for this question
        correct_opt_value_selected = form_data.get(f'q_{q_index}_opt_correct') # e.g., 'dyn_1743803451168'
        print(correct_opt_value_selected)
        logger.debug(f"Q_Index: {q_index} - Correct Option Value Selected: {correct_opt_value_selected}")

        for text_key in option_text_keys:
            # Extract the unique option index ('dyn_...') from the key
            try:
                # Split by 'opt_text_' to get the dynamic index part
                opt_index = text_key.split('opt_text_')[1]
                if not opt_index:
                    logger.warning(f"Could not parse option index from key: {text_key}")
                    continue
            except (IndexError, ValueError):
                logger.warning(f"Could not parse option index from key: {text_key}")
                continue

            opt_text = form_data.get(text_key, '').strip()
            print(opt_index)
            if opt_text: # Only include options that have text
                # Determine if this option was the one selected as correct
                is_correct = (opt_index == correct_opt_value_selected)
                options_data.append({"text": opt_text, "is_correct": is_correct})
                logger.debug(f"  Opt Index: {opt_index}, Text: '{opt_text}', Correct: {is_correct}")
        print(options_data)
        # Basic validation (moved here for clarity after parsing)
        if not q_delete:
            if len(options_data) < 2:
                 logger.warning(f"Skipping question index {q_index}: Less than 2 valid options found.")
                 continue
            if not any(opt['is_correct'] for opt in options_data):
                 logger.warning(f"Skipping question index {q_index}: No correct option was effectively selected/submitted.")
                 continue # Need a correct answer if not deleting
        # Append the fully parsed question data
        questions_to_save.append({
            "id": q_id_str, # Pass original ID string ('5', '', 'new_X')
            "question_text": q_text,
            "marks": q_marks_str, # Service validates/converts
            "options": options_data, # Parsed list of option dicts
            "delete": q_delete
        })

    logger.debug(f"--- Prepared Questions Data for Service (Exam {exam_id}) ---")
    for i, qd in enumerate(questions_to_save): logger.debug(f"Q{i+1}: {qd}")
    logger.debug(f"--- End Prepared Data ---")

    # --- Call Service ---
    redirect_url = request.url_for('instructor_edit_exam_mcqs', exam_id=exam_id)
    query_params = []
    try:
        saved_count, total_marks = exam_service.save_mcq_questions_for_exam(db, exam_id, questions_to_save)
        toast_msg = urllib.parse.quote(f"Saved {saved_count} questions. Exam total marks: {total_marks:.1f}")
        query_params.append(f"toast_success={toast_msg}")
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error saving questions: {e}")
        query_params.append(f"toast_error={toast_msg}")
    except Exception as e:
        logger.error(f"Unexpected error saving MCQs for exam {exam_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        query_params.append(f"toast_error={toast_msg}")

    # --- Redirect ---
    final_redirect_url = f"{redirect_url}?{'&'.join(query_params)}"
    return RedirectResponse(final_redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/exams/define/add", response_class=RedirectResponse, name="instructor_add_exam_definition")
async def add_exam_definition_by_instructor(
     request: Request, db: Session = Depends(database.get_db),
     current_user: models.User = Depends(auth_service.get_current_active_instructor),
     course_id_str: str = Form(...), name: str = Form(...), exam_type_str: str = Form(...),
     exam_date_str: Optional[str] = Form(None), description: Optional[str] = Form(None)
 ):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(403, "Profile needed.")

    # Redirect back to the manage exams page, preserving the selected course filter
    redirect_url = request.url_for('instructor_manage_exams')
    query_params = []
    course_id = None # Keep track for redirect

    try:
        course_id = int(course_id_str)
        query_params.append(f"course_id={course_id}") # Add course_id for redirect


        try: exam_type_enum = models.ExamType(exam_type_str)
        except ValueError: raise ValueError(f"Invalid exam type: {exam_type_str}")
        exam_date = date.fromisoformat(exam_date_str) if exam_date_str and exam_date_str.strip() else None
        new_exam = exam_service.create_exam(db, course_id, name, exam_type_enum, exam_date, description)
        toast_msg = urllib.parse.quote(f"Exam '{new_exam.name}' definition created. Edit questions now.")
        query_params.append(f"toast_success={toast_msg}")

    except ValueError as e: toast_msg = urllib.parse.quote(f"Error adding exam: {e}"); query_params.append(f"toast_error={toast_msg}")
    except Exception as e: logger.error(f"Error adding exam def: {e}"); toast_msg=urllib.parse.quote("Unexpected server error."); query_params.append(f"toast_error={toast_msg}")

    final_redirect_url = f"{redirect_url}?{'&'.join(query_params)}"
    return RedirectResponse(final_redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# EDIT Exam Definition
@router.post("/exams/define/{exam_id}/edit", response_class=RedirectResponse, name="instructor_edit_exam_definition")
async def edit_exam_definition_by_instructor(
     exam_id: int, request: Request, db: Session = Depends(database.get_db),
     current_user: models.User = Depends(auth_service.get_current_active_instructor),
     # Get data from the DEFINITION modal form
     name: str = Form(...),
     exam_type_str: str = Form(...),
     exam_date_str: Optional[str] = Form(None),
     description: Optional[str] = Form(None),
     is_published_str: Optional[str] = Form(None) # Checkbox sends 'on' if checked, otherwise key is absent
 ):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: raise HTTPException(403, "Profile needed.")

    # Redirect back to the exam list page, preserving the course filter
    redirect_url = request.url_for('instructor_manage_exams')
    query_params = []
    update_data = {}

    try:
        # --- Permission Check FIRST ---
        exam = exam_service.get_exam_by_id_with_questions(db, exam_id) # Fetch exam to check ownership and get course_id
        if not exam: raise ValueError("Exam not found.")
        query_params.append(f"course_id={exam.course_id}") # Add course_id for redirect filter


        # --- Prepare Update Data ---
        update_data['name'] = name.strip()
        try: update_data['type'] = models.ExamType(exam_type_str) # Convert string value to Enum
        except ValueError: raise ValueError(f"Invalid exam type: {exam_type_str}")
        update_data['date'] = date.fromisoformat(exam_date_str) if exam_date_str and exam_date_str.strip() else None
        # Handle description potentially being absent if textarea is empty
        update_data['description'] = description.strip() if description is not None else None
        # Handle checkbox: 'on' if checked, otherwise it won't be in form data (or browser might send default)
        # We check if the key was sent with value 'on'
        update_data['is_published'] = (is_published_str == 'on')
        # --- End Prepare Update Data ---

        logger.debug(f"Updating exam {exam_id} definition with data: {update_data}")

        # --- Call Service to Update Details ---
        updated_exam = exam_service.update_exam_details(db, exam_id, update_data)
        # update_exam_details returns None if not found, but we checked already
        if updated_exam is None: raise ValueError("Exam update failed unexpectedly.")

        toast_msg = urllib.parse.quote(f"Exam '{updated_exam.name}' details updated.")
        query_params.append(f"toast_success={toast_msg}")

    except ValueError as e:
        logger.warning(f"Failed to update exam definition {exam_id}: {e}")
        toast_msg = urllib.parse.quote(f"Error updating exam: {e}")
        query_params.append(f"toast_error={toast_msg}")
        # If exam object was fetched, ensure course_id is still in query_params
        if 'exam' in locals() and exam:
             if f"course_id={exam.course_id}" not in query_params:
                 query_params.append(f"course_id={exam.course_id}")
    except Exception as e:
        logger.error(f"Unexpected error updating exam def {exam_id}: {e}", exc_info=True)
        toast_msg=urllib.parse.quote("Unexpected server error during update.")
        query_params.append(f"toast_error={toast_msg}")
        # Try to keep course_id if possible
        if 'exam' in locals() and exam:
             if f"course_id={exam.course_id}" not in query_params:
                 query_params.append(f"course_id={exam.course_id}")


    # --- Redirect ---
    # Ensure redirect URL doesn't have duplicate query params if error occurred after adding course_id
    final_query_string = '&'.join(list(dict.fromkeys(query_params))) # Basic duplicate removal if needed
    final_redirect_url = f"{redirect_url}?{final_query_string}"
    logger.info(f"Redirecting after exam definition update/add attempt to: {final_redirect_url}")
    return RedirectResponse(final_redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# DELETE Exam Definition
@router.post("/exams/define/{exam_id}/delete", response_class=JSONResponse, name="instructor_delete_exam_definition")
async def delete_exam_definition_by_instructor(
     exam_id: int, db: Session = Depends(database.get_db),
     current_user: models.User = Depends(auth_service.get_current_active_instructor)
 ):
    instructor_profile = current_user.instructor_profile
    if not instructor_profile: return JSONResponse(status_code=403, content={"success": False, "message": "Profile needed."})
    try:
        # Permission check inside try block
        exam = exam_service.get_exam_by_id_with_questions(db, exam_id)
        if not exam: raise ValueError("Exam not found.")


        success = exam_service.delete_exam(db, exam_id) # Service checks results dependency
        # The service raises ValueError if deletion fails due to dependency or other DB error
        return JSONResponse(content={"success": True, "message": "Exam definition deleted."})

    except ValueError as e: return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e: logger.error(f"Error deleting exam def {exam_id}: {e}"); return JSONResponse(status_code=500, content={"success": False, "message": "Unexpected error."})
