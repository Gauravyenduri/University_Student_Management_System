# app/routes/schedule.py

from fastapi import (
    APIRouter, Depends, Request, Form, HTTPException, status, Query, Response,
    Body # Import Body for potential JSON response later
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse # Add JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import urllib.parse
import json

# Local imports
from app import database, models
from app.services import (
    auth_service, schedule_service, course_service,
    instructor_service, classroom_service
)
from app.models import UserRole, Schedule

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Schedules ===

# READ (List Schedules) - Remains largely the same
@router.get("/", response_class=HTMLResponse, name="admin_manage_schedules_list")
async def list_schedules_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    # Query params for toast messages on initial load after redirect
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    schedules = schedule_service.get_all_schedules(db)
    courses = course_service.get_all_courses(db)
    instructors = instructor_service.get_all_instructors(db)
    classrooms = classroom_service.get_all_classrooms(db)

    # Prepare data as JSON for JavaScript
    courses_json = json.dumps([{"id": c.id, "name": c.name} for c in courses])
    instructors_json = json.dumps([{"id": i.id, "name": i.name} for i in instructors])
    classrooms_json = json.dumps([{"id": r.id, "location": r.location} for r in classrooms])
    schedules_data = [ # Detailed schedule data for grid generation
        { "id": s.id, "course_id": s.course_id, "course_name": s.course.name if s.course else "N/A", "instructor_id": s.instructor_id, "instructor_name": s.instructor.name if s.instructor else "N/A", "classroom_id": s.classroom_id, "classroom_location": s.classroom.location if s.classroom else "N/A", "day_of_week": s.day_of_week, "start_time": s.start_time, "end_time": s.end_time, }
        for s in schedules
    ]
    schedules_json = json.dumps(schedules_data)

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "schedules_json": schedules_json, "courses_json": courses_json,
        "instructors_json": instructors_json, "classrooms_json": classrooms_json,
        "page_title": "Manage Course Schedules",
        # Pass toast messages directly
        "toast_error": toast_error,
        "toast_success": toast_success
    }
    return templates.TemplateResponse("admin/schedules_list.html", context)


# CREATE (Process Add Schedule Form) - Still redirects, passes toast message in URL
@router.post("/add", response_class=RedirectResponse, name="admin_manage_schedule_add")
async def add_schedule_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    course_id_str: str = Form(...), instructor_id_str: str = Form(...),
    classroom_id_str: Optional[str] = Form(None), day_of_week: str = Form(...),
    start_time: str = Form(...), end_time: str = Form(...)
):
    redirect_url = request.url_for('admin_manage_schedules_list')
    try:
        # Basic time validation (start before end)
        if start_time >= end_time:
             raise ValueError("End time must be after start time.")

        course_id = int(course_id_str); instructor_id = int(instructor_id_str)
        classroom_id = int(classroom_id_str) if classroom_id_str and classroom_id_str.strip() else None

        new_schedule = schedule_service.create_schedule(
            db=db, course_id=course_id, instructor_id=instructor_id, classroom_id=classroom_id,
            day_of_week=day_of_week, start_time=start_time, end_time=end_time
        )
        logger.info(f"Admin {current_user.username} created schedule {new_schedule.id}")
        toast_msg = urllib.parse.quote("Schedule created successfully.")
        return RedirectResponse(url=f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        logger.warning(f"Admin {current_user.username} failed to add schedule: {e}")
        toast_msg = urllib.parse.quote(f"Error adding schedule: {e}")
        return RedirectResponse(url=f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} unexpected error adding schedule: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred while adding the schedule.")
        return RedirectResponse(url=f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# UPDATE (Process Edit Schedule Form) - Still redirects, passes toast message in URL
@router.post("/{schedule_id}/edit", response_class=RedirectResponse, name="admin_manage_schedule_edit")
async def edit_schedule_by_admin(
    schedule_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    course_id_str: str = Form(...), instructor_id_str: str = Form(...),
    classroom_id_str: Optional[str] = Form(None), day_of_week: str = Form(...),
    start_time: str = Form(...), end_time: str = Form(...)
):
    redirect_url = request.url_for('admin_manage_schedules_list')
    update_data = {}
    try:
         # Basic time validation
        if start_time >= end_time:
             raise ValueError("End time must be after start time.")

        update_data['course_id'] = int(course_id_str)
        update_data['instructor_id'] = int(instructor_id_str)
        update_data['classroom_id'] = int(classroom_id_str) if classroom_id_str and classroom_id_str.strip() else None
        update_data['day_of_week'] = day_of_week
        update_data['start_time'] = start_time
        update_data['end_time'] = end_time

        updated_schedule = schedule_service.update_schedule(
            db=db, schedule_id=schedule_id, update_data=update_data
        )
        if updated_schedule is None: raise ValueError("Schedule not found.")

        logger.info(f"Admin {current_user.username} updated schedule {schedule_id}")
        toast_msg = urllib.parse.quote("Schedule updated successfully.")
        return RedirectResponse(url=f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        logger.warning(f"Admin {current_user.username} failed to update schedule {schedule_id}: {e}")
        toast_msg = urllib.parse.quote(f"Error updating schedule: {e}")
        return RedirectResponse(url=f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} unexpected error updating schedule {schedule_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred while updating the schedule.")
        return RedirectResponse(url=f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# DELETE Schedule - Returns JSON for fetch request
# Note: Changed response_class
@router.post("/{schedule_id}/delete", response_class=JSONResponse, name="admin_manage_schedule_delete")
async def delete_schedule_by_admin(
    schedule_id: int,
    # request: Request, # No longer needed for redirect URL
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    try:
        success = schedule_service.delete_schedule(db=db, schedule_id=schedule_id)
        if not success:
             # This case might not be reachable if service raises ValueError for not found
             logger.warning(f"Admin {current_user.username} delete failed: Schedule {schedule_id} not found by service.")
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")

        logger.info(f"Admin {current_user.username} deleted schedule {schedule_id}")
        # Return success JSON
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": True, "message": "Schedule deleted successfully."}
        )
    except ValueError as e: # Catch errors like "cannot delete", "not found" from service
         logger.warning(f"Admin {current_user.username} failed to delete schedule {schedule_id}: {e}")
         # Return error JSON
         return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, # Or 404 if appropriate
            content={"success": False, "message": str(e)}
        )
    except Exception as e:
        logger.error(f"Admin {current_user.username} unexpected error deleting schedule {schedule_id}: {e}", exc_info=True)
        # Return generic error JSON
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": "An unexpected error occurred while deleting the schedule."}
        )