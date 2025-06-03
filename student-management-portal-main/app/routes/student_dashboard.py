from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from typing import Optional, Dict
import logging
import os
import json
from datetime import date
import urllib.parse # For encoding toast messages
from app.services import auth_service, enrollment_service
from sqlalchemy import func
# Local imports
from app import database, models
from app.services import auth_service, student_service # student_service needed here now
from app.models import UserRole, User, Student
from app.services import attendance_service, library_service # Make sure attendance_service is imported


logger = logging.getLogger(__name__)
router = APIRouter() # Keep prefix if desired
templates = Jinja2Templates(directory="app/templates")

# === Student Dashboard Route (Keep as is, potentially simplify later) ===
@router.get("/dashboard", response_class=HTMLResponse, name="student_dashboard")
async def get_student_dashboard(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the overview dashboard for the logged-in student."""
    logger.info(f"Accessing student dashboard overview for user: {current_user.username}")

    student_profile = current_user.student_profile
    dashboard_data = {
        "enrolled_courses_count": 0,
        "attendance_percentage": None, # Initialize as None
        "overall_gpa": None, # Initialize as None
        "upcoming_assignments_count": 0, # Placeholder
        "pending_fees_count": 0 # Placeholder
    }

    if student_profile:
        try:
            # 1. Count Enrolled Courses
            dashboard_data["enrolled_courses_count"] = db.query(func.count(models.Enrollment.id)).filter(
                models.Enrollment.student_id == student_profile.id
            ).scalar() or 0

            # 2. Calculate Attendance Percentage (Example: Overall)
            total_attendance_records = db.query(func.count(models.Attendance.id)).filter(
                models.Attendance.student_id == student_profile.id
            ).scalar() or 0

            if total_attendance_records > 0:
                present_count = db.query(func.count(models.Attendance.id)).filter(
                    models.Attendance.student_id == student_profile.id,
                    models.Attendance.status == models.AttendanceStatus.PRESENT # Use Enum value
                ).scalar() or 0
                # Calculate percentage, handle division by zero
                dashboard_data["attendance_percentage"] = round((present_count / total_attendance_records) * 100, 1) if total_attendance_records > 0 else 0.0
            else:
                 dashboard_data["attendance_percentage"] = 100.0 # Or None/N/A if no records yet


            # 3. Calculate Overall GPA (Simplified Example - NEEDS proper grade point logic)
            # This is highly dependent on how grades/credits map to points.
            # Assuming Grade model has 'grade' (A, B, C..) and Course has 'credits'
            # grades_with_credits = db.query(models.Grade.grade, models.Course.credits)\
            #     .join(models.Course, models.Grade.course_id == models.Course.id)\
            #     .filter(models.Grade.student_id == student_profile.id)\
            #     .filter(models.Grade.grade.isnot(None))\
            #     .filter(models.Course.credits.isnot(None))\
            #     .all()

            # if grades_with_credits:
            #     total_points = 0
            #     total_credits = 0
            #     grade_point_map = {'A': 4.0, 'B': 3.0, 'C': 2.0, 'D': 1.0, 'F': 0.0} # Example map
            #     for grade, credits in grades_with_credits:
            #         points = grade_point_map.get(grade.upper(), 0.0) # Default to 0 if grade not in map
            #         if credits > 0: # Only count courses with credits
            #             total_points += points * credits
            #             total_credits += credits
            #     dashboard_data["overall_gpa"] = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

            # 4. Count Pending Fees (Example)
            dashboard_data["pending_fees_count"] = db.query(func.count(models.FeePayment.id)).filter(
                models.FeePayment.student_id == student_profile.id,
                models.FeePayment.status.in_([models.PaymentStatus.PENDING, models.PaymentStatus.OVERDUE, models.PaymentStatus.PENDING]) # Example pending states
            ).scalar() or 0

            # 5. Upcoming Assignments/Exams (Placeholder - would require Exam/Assignment model with due dates)
            # dashboard_data["upcoming_assignments_count"] = ... query exams/assignments ...

        except Exception as e:
            logger.error(f"Error fetching dashboard summary data for student {student_profile.id}: {e}", exc_info=True)
            toast_error = "Could not load all dashboard summary data."

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user,
        "student_profile": student_profile,
        "UserRole": UserRole,
        "page_title": "Student Dashboard",
        "dashboard_data": dashboard_data, # Pass the summary data
        "toast_error": toast_error,
        "toast_success": toast_success
    }
    return templates.TemplateResponse("student/student_dashboard.html", context)


# === NEW: Student Enrollment Management Page Route ===
@router.get("/enrollments", response_class=HTMLResponse, name="student_enrollments_page")
async def get_student_enrollment_page(
    request: Request,
    response: Response, # Inject response for cache headers
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the page for managing course enrollments."""
    logger.info(f"Accessing enrollment page for user: {current_user.username}")

    student_profile = current_user.student_profile
    current_enrollments = []
    available_courses = []
    if student_profile:
        try:
            current_enrollments = enrollment_service.get_enrollments_for_student(db, student_profile.id)
            available_courses = enrollment_service.get_available_courses_for_student(db, student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching enrollment data for student {student_profile.id}: {e}", exc_info=True)
            # Pass error message to be displayed on the page?
            toast_error = "Could not load enrollment data." # Override or append?

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user, # Needed for layout
        "student_profile": student_profile, # Needed? Maybe just for display consistency.
        "UserRole": UserRole, # Needed for layout
        "page_title": "My Enrollments", # Page specific title
        "current_enrollments": current_enrollments,
        "available_courses": available_courses,
        "toast_error": toast_error, # Pass messages
        "toast_success": toast_success
    }
    # Render the new enrollment template
    return templates.TemplateResponse("student/enrollment.html", context)


# === Enroll Route (Update Redirect) ===
@router.post("/enroll", response_class=RedirectResponse, name="student_enroll")
async def handle_student_enroll(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    course_id: int = Form(...)
):
    # >>> CHANGE: Redirect back to the enrollments page <<<
    redirect_url = request.url_for('student_enrollments_page')
    # ... (rest of the logic remains the same, using redirect_url) ...
    if not current_user.student_profile: # Check profile
         toast_msg = urllib.parse.quote("Cannot enroll: Student profile not found.")
         return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    try:
        enrollment = enrollment_service.create_enrollment(db, student_id=current_user.student_profile.id, course_id=course_id)
        toast_msg = urllib.parse.quote(f"Successfully enrolled.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Enrollment failed: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Enrollment error: StudID {current_user.student_profile.id}, CourseID {course_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# === Unenroll Route (Update Redirect) ===
@router.post("/unenroll/{enrollment_id}", response_class=RedirectResponse, name="student_unenroll")
async def handle_student_unenroll(
    request: Request, enrollment_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    # >>> CHANGE: Redirect back to the enrollments page <<<
    redirect_url = request.url_for('student_enrollments_page')
    # ... (rest of the logic remains the same, using redirect_url) ...
    if not current_user.student_profile: # Check profile
         toast_msg = urllib.parse.quote("Cannot unenroll: Student profile not found.")
         return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    try:
        success = enrollment_service.delete_enrollment(db, enrollment_id=enrollment_id, student_id=current_user.student_profile.id)
        if not success: raise ValueError("Enrollment not found or permission denied.")
        toast_msg = urllib.parse.quote("Successfully unenrolled from course.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Unenrollment failed: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unenrollment error: EnrollID {enrollment_id}, StudID {current_user.student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

@router.get("/my-schedule", response_class=HTMLResponse, name="student_schedule_page")
async def get_student_schedule_page(
    request: Request,
    response: Response, # Inject response for cache headers
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student), # Ensures student role
):
    """Displays the student's personal course schedule."""
    logger.info(f"Accessing schedule page for user: {current_user.username}")

    student_profile = current_user.student_profile
    student_schedule_entries = []

    if student_profile:
        try:
            # Fetch enrollments first to know which courses the student takes
            enrollments = enrollment_service.get_enrollments_for_student(db, student_profile.id)
            enrolled_course_ids = [e.course_id for e in enrollments]

            if enrolled_course_ids:
                # Fetch schedule entries ONLY for the courses the student is enrolled in
                student_schedule_entries = db.query(models.Schedule).options(
                    joinedload(models.Schedule.course),
                    joinedload(models.Schedule.instructor), # No need for instructor.user here? Optional.
                    joinedload(models.Schedule.classroom)
                ).filter(
                    models.Schedule.course_id.in_(enrolled_course_ids) # Filter by enrolled courses
                ).order_by(models.Schedule.day_of_week, models.Schedule.start_time).all()

        except Exception as e:
            logger.error(f"Error fetching schedule data for student {student_profile.id}: {e}", exc_info=True)
            # Can optionally pass an error message via context if needed

    # Prepare schedule data as JSON for JavaScript grid generation
    schedules_data = [
        {
            # No 'id' needed if not editing/deleting
            "course_name": s.course.name if s.course else "N/A",
            "instructor_name": s.instructor.name if s.instructor else "N/A",
            "classroom_location": s.classroom.location if s.classroom else "N/A",
            "day_of_week": s.day_of_week,
            "start_time": s.start_time,
            "end_time": s.end_time,
        } for s in student_schedule_entries
    ]
    schedules_json = json.dumps(schedules_data)

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user, # Needed for layout
        "student_profile": student_profile, # For potential display/checks
        "UserRole": UserRole, # Needed for layout
        "page_title": "My Class Schedule", # Page specific title
        "schedules_json": schedules_json, # Pass schedule data as JSON
        # No need for toast messages here unless there was an action leading here
    }
    # Render the new schedule template
    return templates.TemplateResponse("student/my_schedule.html", context)

@router.get("/my-attendance", response_class=HTMLResponse, name="student_attendance_page")
async def get_student_attendance_page(
    request: Request,
    response: Response, # For cache control
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Optional Query Params for Filtering
    filter_course_id: Optional[int] = Query(None),
    filter_start_date: Optional[date] = Query(None),
    filter_end_date: Optional[date] = Query(None)
):
    """Displays the logged-in student's attendance records."""
    logger.info(f"Accessing attendance page for user: {current_user.username}")

    student_profile = current_user.student_profile
    attendance_records = []
    courses_enrolled = [] # For filter dropdown

    if student_profile:
        try:
            # Fetch enrolled courses for the filter dropdown
            enrollments = enrollment_service.get_enrollments_for_student(db, student_profile.id)
            courses_enrolled = sorted([e.course for e in enrollments if e.course], key=lambda c: c.name)

            # Fetch attendance records using the service function with filters
            attendance_records = attendance_service.get_attendance_for_student(
                db,
                student_id=student_profile.id,
                course_id=filter_course_id, # Use filter_course_id
                start_date=filter_start_date,
                end_date=filter_end_date
            )

        except Exception as e:
            logger.error(f"Error fetching attendance data for student {student_profile.id}: {e}", exc_info=True)
            # Optionally set a toast error message via context or rely on general error handling

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user, # Needed for layout
        "student_profile": student_profile, # May be needed for display
        "UserRole": UserRole, # Needed for layout
        "page_title": "My Attendance Report", # Page specific title
        "attendance_records": attendance_records,
        "courses_enrolled": courses_enrolled, # For filter dropdown
        # Pass current filter values back to template to populate form
        "current_filter_course_id": filter_course_id,
        "current_filter_start_date": filter_start_date.isoformat() if filter_start_date else "",
        "current_filter_end_date": filter_end_date.isoformat() if filter_end_date else ""
        # No toast messages needed unless an action redirects here
    }
    # Render the new attendance template
    return templates.TemplateResponse("student/my_attendance.html", context)


from app.services import exam_service

from app.services import result_service # Import result service


@router.get("/exams/{exam_id}/attempt", response_class=HTMLResponse, name="student_attempt_exam")
async def attempt_exam_page(
    request: Request,
    exam_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    student_profile = current_user.student_profile
    if not student_profile: raise HTTPException(403, "Student profile required.")

    # 1. Check if exam exists, is published, and student is enrolled
    exam = exam_service.get_published_exam_details_for_student(db, exam_id, student_profile.id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found, not published, or you are not enrolled in the course.")

    # 2. Check if already submitted
    # Note: Allow viewing even if submitted? Or redirect to results? Let's prevent re-attempt for now.
    if exam_service.check_exam_attempt_exists(db, exam_id, student_profile.id):
        logger.warning(f"Student {student_profile.id} attempted to re-access exam {exam_id} already submitted.")
        # Redirect to results page or dashboard with error?
        redirect_url = request.url_for('student_exams_page')
        toast_msg = urllib.parse.quote("You have already submitted this exam.")
        # Using 303 See Other to indicate the resource state has changed (already submitted)
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Fetch questions prepared for student (no correct answers)
    questions = exam_service.get_exam_questions_for_student(db, exam_id)

    context = {
        "request": request,
        "user": current_user, # For layout
        "UserRole": UserRole, # For layout
        "exam": exam,
        "questions": questions,
        "page_title": f"Attempt: {exam.name}",
    }
    # Create app/templates/student/attempt_exam.html
    return templates.TemplateResponse("student/attempt_exam.html", context)


# POST: Submit Exam Answers
@router.post("/exams/{exam_id}/submit", response_class=RedirectResponse, name="student_submit_exam")
async def submit_exam_answers(
    request: Request,
    exam_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    student_profile = current_user.student_profile
    if not student_profile: raise HTTPException(403, "Student profile required.")

    # Redirect back to the main exam list page after submission
    redirect_url = request.url_for('student_exams_page')

    # --- Permission/Pre-check ---
    # Check if exam exists, is published, and student is enrolled (redundant? Service does it too)
    exam = exam_service.get_published_exam_details_for_student(db, exam_id, student_profile.id)
    if not exam:
         toast_msg = urllib.parse.quote("Exam not found or access denied.")
         return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
     # Check if already submitted (Service will raise error too, but good to check early)
    if exam_service.check_exam_attempt_exists(db, exam_id, student_profile.id):
        toast_msg = urllib.parse.quote("Exam already submitted.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    # --- Process Form Data ---
    form_data = await request.form()
    submitted_answers: Dict[int, str] = {} # {question_id: selected_option_text}

    for key, value in form_data.items():
        if key.startswith("q_answer_"): # Name convention for radio groups per question
             try:
                 question_id = int(key.split("_")[-1])
                 selected_option_text = value # Value of the radio is the option text
                 submitted_answers[question_id] = selected_option_text
             except (ValueError, IndexError):
                 logger.warning(f"Could not parse answer form key: {key}")

    logger.debug(f"Student {student_profile.id} submitting answers for exam {exam_id}: {submitted_answers}")

    # --- Call Result Service ---
    try:
        result = result_service.record_exam_submission(
            db=db,
            exam_id=exam_id,
            student_id=student_profile.id,
            submitted_answers=submitted_answers
        )
        score_percent = (result.score / exam.total_marks * 100) if exam.total_marks else 0
        toast_msg = urllib.parse.quote(f"Exam submitted successfully! Score: {result.score:.1f}/{exam.total_marks:.1f} ({score_percent:.1f}%)")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Submission Error: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error submitting exam {exam_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred during submission.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

from app.models import Result
from fastapi.responses import JSONResponse

@router.get("/my-exams", response_class=HTMLResponse, name="student_exams_page")
async def get_student_exams_page(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    """Displays published exams, indicating which have been attempted."""
    student_profile = current_user.student_profile
    published_exams = []
    results_map = {} # Map exam_id -> Result object
    error_message = None
    if student_profile:
        try:
            # Fetch published exams for student's courses
            published_exams = exam_service.get_published_exams_for_student_courses(db, student_profile.id)

            # --- ADDED: Fetch existing results for these exams ---
            if published_exams:
                exam_ids = [exam.id for exam in published_exams]
                existing_results = db.query(Result).filter(
                    Result.student_id == student_profile.id,
                    Result.exam_id.in_(exam_ids)
                ).all()
                # Create map for easy lookup in template: {exam_id: result_object}
                results_map = {result.exam_id: result for result in existing_results}
                logger.debug(f"Found {len(results_map)} existing results for student {student_profile.id}")
            # --- END ADDED ---
            

        except Exception as e:
            logger.error(f"Error fetching data for student exams page {student_profile.id}: {e}", exc_info=True)
            error_message = "Could not load exam list or results."
    else:
        error_message = "Student profile not found."

    # ... (set cache headers) ...
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.

    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "page_title": "My Exams & Assignments",
        "published_exams": published_exams,
        "results_map": results_map, # <<<< PASS THE RESULTS MAP
        "error_message": error_message
    }
    return templates.TemplateResponse("student/my_exams.html", context)

# ... (rest of student_dashboard.py: attempt_exam_page, submit_exam_answers, enroll, unenroll) ...

# === NEW: Route to View Exam Result Details ===
@router.get("/results/{result_id}", response_class=HTMLResponse, name="student_view_result")
async def view_exam_result_page(
    request: Request,
    result_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    """Displays the detailed results of a specific exam attempt."""
    student_profile = current_user.student_profile
    if not student_profile: raise HTTPException(403, "Student profile required.")

    # Fetch result details including answers and related question/exam info
    result_details = result_service.get_result_details_with_answers(db, result_id, student_profile.id)

    if not result_details:
        raise HTTPException(status_code=404, detail="Result not found or you do not have permission to view it.")
    print(result_details)
    context = {
        "request": request,
        "user": current_user, # For layout
        "UserRole": UserRole, # For layout
        "result": result_details, # Pass the detailed result object
        "page_title": f"Result: {result_details.exam.name}"
    }
    return templates.TemplateResponse("student/my_exam_result.html", context)

from app.services import fee_service # Import fee service

@router.get("/my-fees", response_class=HTMLResponse, name="student_fees_page")
async def get_student_fees_page(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    student_profile = current_user.student_profile
    fee_records = []
    if student_profile:
        try:
            # Get all fee records for this student
            fee_records = fee_service.get_all_fee_payments(db, student_id=student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching fees for student {student_profile.id}: {e}")
            toast_error = "Could not load fee information."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "fee_records": fee_records,
        "page_title": "My Fee Payments",
        "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("student/my_fees.html", context)


# === NEW: Student Pays Fee ===
@router.post("/fees/{payment_id}/pay", response_class=RedirectResponse, name="student_pay_fee")
async def handle_student_fee_payment(
    request: Request,
    payment_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    # Redirect back to the student fees page
    redirect_url = request.url_for('student_fees_page')
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Cannot pay fee: Student profile not found.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        paid_fee = fee_service.record_student_payment(db, payment_id, student_profile.id)
        if not paid_fee:
            # This case is handled by ValueError in service usually, but good check
            raise ValueError("Fee record not found or payment failed.")

        toast_msg = urllib.parse.quote(f"Payment recorded successfully for fee record {payment_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Payment failed: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error during fee payment {payment_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred during payment.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

@router.get("/my-library", response_class=HTMLResponse, name="student_library_page")
async def get_student_library_page(
    request: Request,
    response: Response, # For cache control
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    """Displays the logged-in student's library borrowing records."""
    logger.info(f"Accessing library records page for user: {current_user.username}")

    student_profile = current_user.student_profile
    library_records = []
    error_message = None

    if student_profile:
        try:
            # Fetch records only for this student
            library_records = library_service.get_all_library_records(db, student_id=student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching library records for student {student_profile.id}: {e}", exc_info=True)
            error_message = "Could not load your library records."
    else:
        error_message = "Student profile not found."

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user, # For layout
        "UserRole": UserRole, # For layout
        "page_title": "My Library Records", # Page specific title
        "library_records": library_records,
        "error_message": error_message # Pass potential errors
    }
    # Render the new library record template for students
    return templates.TemplateResponse("student/my_library_records.html", context)

from app.services import student_service, guardian_service # Import services

# ... (logger, router, templates, other student routes: dashboard, enrollments, schedule, attendance, exams, fees) ...


# === NEW: Student Profile Page Route ===
@router.get("/profile", response_class=HTMLResponse, name="student_profile_page")
async def get_student_profile_page(
    request: Request,
    response: Response, # For cache control
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the student's profile and guardian management page."""
    logger.info(f"Accessing profile page for user: {current_user.username}")

    student_profile = current_user.student_profile # Fetch profile via user relationship
    guardians = []
    error_message = None

    if student_profile:
        try:
            # Fetch associated guardians using the service
            guardians = guardian_service.get_guardians_for_student(db, student_id=student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching guardians for student {student_profile.id}: {e}", exc_info=True)
            error_message = "Could not load guardian information."
    else:
        error_message = "Student profile not found."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "student_profile": student_profile, # Pass profile (can be None)
        "guardians": guardians,             # Pass list of guardians
        "page_title": "My Profile & Guardians",
        "toast_error": toast_error or error_message, # Show fetch error if any
        "toast_success": toast_success
    }
    # New template path
    return templates.TemplateResponse("student/my_profile.html", context)


# === NEW: Update Student Profile Details ===
@router.post("/profile/update", response_class=RedirectResponse, name="student_update_profile")
async def handle_student_profile_update(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Form fields for student details
    name: str = Form(...),
    dob_str: Optional[str] = Form(None)
    # Add phone: Optional[str] = Form(None), address: Optional[str] = Form(None) if editable
):
    redirect_url = request.url_for('student_profile_page')
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile not found, cannot update.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    update_data = {}
    try:
        if not name or not name.strip(): raise ValueError("Name cannot be empty.")
        update_data['name'] = name.strip()
        update_data['dob'] = date.fromisoformat(dob_str) if dob_str else None
        # Add phone/address if implemented
        # update_data['phone'] = phone ...

        updated_profile = student_service.update_student_profile(db, student_profile.id, update_data)
        # No need to check return value if service raises error on failure

        toast_msg = urllib.parse.quote("Profile details updated successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating profile: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating profile for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# === NEW: Add Guardian ===
@router.post("/guardians/add", response_class=RedirectResponse, name="student_add_guardian")
async def handle_student_add_guardian(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Form fields from guardian modal
    g_name: str = Form(..., alias="guardian_name"), # Use alias if HTML name differs
    g_relationship: Optional[str] = Form(None, alias="guardian_relationship"),
    g_phone: Optional[str] = Form(None, alias="guardian_phone"),
    g_email: Optional[str] = Form(None, alias="guardian_email"),
    g_address: Optional[str] = Form(None, alias="guardian_address")
):
    redirect_url = request.url_for('student_profile_page')
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile not found, cannot add guardian.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        new_guardian = guardian_service.add_guardian_for_student(
            db, student_id=student_profile.id, name=g_name, relationship_type=g_relationship,
            phone=g_phone, email=g_email, address=g_address
        )
        toast_msg = urllib.parse.quote(f"Guardian '{new_guardian.name}' added.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding guardian: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding guardian for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred adding guardian.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# === NEW: Edit Guardian ===
@router.post("/guardians/{guardian_id}/edit", response_class=RedirectResponse, name="student_edit_guardian")
async def handle_student_edit_guardian(
    request: Request,
    guardian_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Form fields from guardian modal
    g_name: str = Form(..., alias="guardian_name"),
    g_relationship: Optional[str] = Form(None, alias="guardian_relationship"),
    g_phone: Optional[str] = Form(None, alias="guardian_phone"),
    g_email: Optional[str] = Form(None, alias="guardian_email"),
    g_address: Optional[str] = Form(None, alias="guardian_address")
):
    redirect_url = request.url_for('student_profile_page')
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile not found, cannot edit guardian.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    update_data = {
        "name": g_name, "relationship_type": g_relationship, "phone": g_phone,
        "email": g_email, "address": g_address
    }
    try:
        # Service function includes check that guardian belongs to student
        updated_guardian = guardian_service.update_guardian(db, guardian_id, student_profile.id, update_data)
        if updated_guardian is None: raise ValueError("Guardian not found or permission denied.")

        toast_msg = urllib.parse.quote(f"Guardian '{updated_guardian.name}' updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating guardian: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating guardian {guardian_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred updating guardian.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# === NEW: Delete Guardian ===
@router.post("/guardians/{guardian_id}/delete", response_class=JSONResponse, name="student_delete_guardian")
async def handle_student_delete_guardian(
    guardian_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    student_profile = current_user.student_profile
    if not student_profile:
        return JSONResponse(status_code=403, content={"success": False, "message": "Profile not found."})

    try:
        # Service includes check that guardian belongs to student
        success = guardian_service.delete_guardian(db, guardian_id, student_profile.id)
        if not success: raise ValueError("Guardian not found or permission denied.")
        return JSONResponse(content={"success": True, "message": "Guardian deleted."})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting guardian {guardian_id} for student {student_profile.id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": "Unexpected error."})

from app.services import club_service

# ... (logger, router, templates, other student routes) ...


# === NEW: Student Club Management Page ===
@router.get("/my-clubs", response_class=HTMLResponse, name="student_clubs_page")
async def get_student_clubs_page(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the page for student to manage club memberships."""
    logger.info(f"Accessing clubs page for user: {current_user.username}")

    student_profile = current_user.student_profile
    joined_clubs_data = [] # List of StudentClub objects
    available_clubs = [] # List of Club objects
    error_message = None

    if student_profile:
        try:
            # Fetch clubs student has joined (includes Club details via relationship)
            joined_clubs_data = club_service.get_clubs_joined_by_student(db, student_profile.id)
            # Fetch clubs student has NOT joined
            available_clubs = club_service.get_clubs_not_joined_by_student(db, student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching club data for student {student_profile.id}: {e}", exc_info=True)
            error_message = "Could not load club information."
    else:
        error_message = "Student profile not found."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "page_title": "My Clubs & Activities",
        "joined_clubs": joined_clubs_data, # Pass StudentClub objects
        "available_clubs": available_clubs, # Pass Club objects
        "toast_error": toast_error or error_message,
        "toast_success": toast_success,
        "student_profile": student_profile # Pass profile for checks if needed
    }
    return templates.TemplateResponse("student/my_clubs.html", context)


# === NEW: Student Joins Club ===
@router.post("/clubs/join", response_class=RedirectResponse, name="student_join_club")
async def handle_student_join_club(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    club_id: int = Form(...) # ID of the club to join
):
    redirect_url = request.url_for('student_clubs_page') # Redirect back to club page
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile needed to join clubs.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        membership = club_service.student_join_club(db, student_profile.id, club_id)
        toast_msg = urllib.parse.quote(f"Successfully joined club!") # Add club name if needed
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Could not join club: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error joining club {club_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# === NEW: Student Leaves Club ===
@router.post("/clubs/leave", response_class=RedirectResponse, name="student_leave_club")
async def handle_student_leave_club(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    club_id: int = Form(...) # ID of the club to leave
):
    redirect_url = request.url_for('student_clubs_page') # Redirect back to club page
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile needed to leave clubs.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        success = club_service.student_leave_club(db, student_profile.id, club_id)
        if not success:
            # This could mean they weren't a member, which isn't strictly an error here
            toast_msg = urllib.parse.quote("You were not a member of that club.")
            return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER) # Use error toast maybe? Or info?

        toast_msg = urllib.parse.quote("Successfully left club.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch other potential service errors
        toast_msg = urllib.parse.quote(f"Could not leave club: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error leaving club {club_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

from app.services import complaint_service

# ... (logger, router, templates, other student routes) ...


# === NEW: Student Complaint Management Routes ===

# GET: List student's own complaints
@router.get("/my-complaints", response_class=HTMLResponse, name="student_complaints_page")
async def get_student_complaints_page(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays the student's submitted complaints."""
    logger.info(f"Accessing complaints page for user: {current_user.username}")

    student_profile = current_user.student_profile
    complaints = []
    error_message = None

    if student_profile:
        try:
            complaints = complaint_service.get_complaints_for_student(db, student_id=student_profile.id)
        except Exception as e:
            logger.error(f"Error fetching complaints for student {student_profile.id}: {e}", exc_info=True)
            error_message = "Could not load your complaints."
    else:
        error_message = "Student profile not found."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "page_title": "My Complaints & Feedback",
        "complaints": complaints,
        "student_profile": student_profile, # Pass for checks if needed
        "toast_error": toast_error or error_message,
        "toast_success": toast_success
    }
    # New template path
    return templates.TemplateResponse("student/my_complaints.html", context)


# POST: Student creates a new complaint
@router.post("/my-complaints/add", response_class=RedirectResponse, name="student_add_complaint")
async def handle_student_add_complaint(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Form fields from modal/form
    description: str = Form(...)
):
    redirect_url = request.url_for('student_complaints_page') # Redirect back to list
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile needed to submit complaint.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        new_complaint = complaint_service.create_complaint(db, student_profile.id, description)
        toast_msg = urllib.parse.quote("Your complaint has been submitted successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error submitting complaint: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding complaint for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# POST: Student updates their OWN complaint (e.g., description if status allows)
@router.post("/my-complaints/{complaint_id}/edit", response_class=RedirectResponse, name="student_edit_complaint")
async def handle_student_edit_complaint(
    request: Request,
    complaint_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
    # Only allow editing description
    description: str = Form(...)
):
    redirect_url = request.url_for('student_complaints_page')
    student_profile = current_user.student_profile
    if not student_profile:
        toast_msg = urllib.parse.quote("Profile needed to edit complaint.");
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

    try:
        updated_complaint = complaint_service.update_student_complaint(db, complaint_id, student_profile.id, description)
        if updated_complaint is None: raise ValueError("Complaint not found or permission denied.")

        toast_msg = urllib.parse.quote("Complaint description updated successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating complaint: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating complaint {complaint_id} for student {student_profile.id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# POST: Student deletes their OWN complaint (if status allows)
@router.post("/my-complaints/{complaint_id}/delete", response_class=JSONResponse, name="student_delete_complaint")
async def handle_student_delete_complaint(
    complaint_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_student),
):
    student_profile = current_user.student_profile
    if not student_profile:
        return JSONResponse(status_code=403, content={"success": False, "message": "Profile needed."})

    try:
        success = complaint_service.delete_student_complaint(db, complaint_id, student_profile.id)
        if not success: raise ValueError("Complaint not found or permission denied.")
        return JSONResponse(content={"success": True, "message": "Complaint deleted."})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting complaint {complaint_id} for student {student_profile.id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": "Unexpected error."})
