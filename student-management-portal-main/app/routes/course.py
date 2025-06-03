# app/routes/course.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import urllib.parse
import json # For passing data to template

# Local imports
from app import database, models
# Import necessary services and models
from app.services import auth_service, course_service, department_service
from app.models import UserRole, Course, Department # Import Department

logger = logging.getLogger(__name__)

# THIS ROUTER WILL BE MOUNTED WITH A PREFIX like /admin/courses in main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Courses ===

# READ (List Courses)
# Final URL: /admin/courses/
@router.get("/", response_class=HTMLResponse, name="admin_manage_courses_list")
async def list_courses_for_admin(
    request: Request,
    response: Response, # Inject Response for cache headers
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    error: Optional[str] = Query(None),
    success: Optional[str] = Query(None)
):
    courses = course_service.get_all_courses(db)
    departments = department_service.get_all_departments(db) # Fetch departments

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "courses": courses,
        "departments": departments, # Pass departments to context
        "departments_json": json.dumps([{"id": d.id, "name": d.name} for d in departments]), # Pass as JSON for JS
        "page_title": "Manage Courses",
        "error_message": error, # Pass messages from query params
        "success_message": success
    }
    return templates.TemplateResponse("admin/courses_list.html", context)

# CREATE (Process Add Course Form)
# Final URL: /admin/courses/add
@router.post("/add", response_class=RedirectResponse, name="admin_manage_course_add")
async def add_course_by_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields from modal
    name: str = Form(...),
    department_id: int = Form(...), # Department is now mandatory
    credits_str: Optional[str] = Form(None), # Credits as string first
    description: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_courses_list')
    credits: Optional[int] = None
    try:
        # Convert credits string to int, allow empty string/None
        if credits_str and credits_str.strip():
            credits = int(credits_str)

        new_course = course_service.create_course(
            db=db, name=name, department_id=department_id, credits=credits, description=description
        )
        logger.info(f"Admin {current_user.username} created course {new_course.id} ('{new_course.name}' in Dept {department_id})")
        success_msg = urllib.parse.quote(f"Course '{new_course.name}' created successfully.")
        # Append success message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?success={success_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch duplicate name or bad credits format
        logger.warning(f"Admin {current_user.username} failed to add course: {e}")
        error_msg = urllib.parse.quote(str(e))
        # Append error message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error adding course: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while adding the course.")
        # Append error message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)

# UPDATE (Process Edit Course Form)
# Final URL: /admin/courses/{course_id}/edit
@router.post("/{course_id}/edit", response_class=RedirectResponse, name="admin_manage_course_edit")
async def edit_course_by_admin(
    course_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields from modal
    name: str = Form(...),
    department_id: int = Form(...), # Department is now mandatory
    credits_str: Optional[str] = Form(None),
    description: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_courses_list')
    credits: Optional[int] = None
    update_data = {
        "department_id": department_id # Always include department
    }
    try:
        # Convert credits and prepare update data
        if credits_str and credits_str.strip():
            credits = int(credits_str)
        # Include credits in update_data only if provided (even if empty string -> None)
        if credits_str is not None:
            update_data['credits'] = credits if credits_str.strip() else None

        update_data['name'] = name
        # Include description only if provided
        if description is not None:
            update_data['description'] = description


        updated_course = course_service.update_course(
            db=db, course_id=course_id, update_data=update_data
        )
        # Service now returns None if not found, raises ValueError for other issues
        if updated_course is None:
             # This case should ideally not happen if the edit button only shows for existing courses
             error_msg = urllib.parse.quote("Course not found.")
             return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)


        logger.info(f"Admin {current_user.username} updated course {course_id}")
        success_msg = urllib.parse.quote(f"Course '{updated_course.name}' updated successfully.")
        # Append success message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?success={success_msg}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e: # Catch duplicate name, bad credits format, dept not found etc.
        logger.warning(f"Admin {current_user.username} failed to update course {course_id}: {e}")
        error_msg = urllib.parse.quote(str(e))
        # Append error message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error updating course {course_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while updating the course.")
        # Append error message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)

# DELETE Course
# Final URL: /admin/courses/{course_id}/delete
@router.post("/{course_id}/delete", response_class=RedirectResponse, name="admin_manage_course_delete")
async def delete_course_by_admin(
    course_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    redirect_url = request.url_for('admin_manage_courses_list')
    course_name_temp = f"ID {course_id}"
    try:
        # Optional: Get name before deleting
        course = course_service.get_course_by_id(db, course_id)
        if course: course_name_temp = course.name

        success = course_service.delete_course(db=db, course_id=course_id)
        if not success:
             # This case means the course existed but deletion failed after dependency check (unlikely with current service logic)
             # Or the course was deleted between the check and the delete call (rare)
             raise ValueError("Course could not be deleted or was not found.")

        logger.info(f"Admin {current_user.username} deleted course {course_id}")
        success_msg = urllib.parse.quote(f"Course '{course_name_temp}' deleted successfully.")
        # Append success message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?success={success_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch "cannot delete due to dependencies", "not found" from service
         logger.warning(f"Admin {current_user.username} failed to delete course {course_id}: {e}")
         error_msg = urllib.parse.quote(str(e))
         # Append error message to redirect URL
         return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error deleting course {course_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while deleting the course.")
        # Append error message to redirect URL
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)
