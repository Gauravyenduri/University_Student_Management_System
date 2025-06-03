# app/routes/instructor.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import os

# Local imports
from app import database, models
# Import BOTH instructor and auth services
from app.services import auth_service, instructor_service, department_service # Need department service
from app.models import UserRole, User, Instructor, Department # Import models

logger = logging.getLogger(__name__)

# THIS ROUTER WILL BE MOUNTED WITH A PREFIX like /admin/instructors in main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Instructors ===

# READ (List Instructors)
# Final URL: /admin/instructors/
@router.get("/", response_class=HTMLResponse, name="admin_manage_instructors_list")
async def list_instructors_for_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    instructors = instructor_service.get_all_instructors(db)
    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "instructors": instructors,
        "page_title": "Manage Instructors"
    }
    return templates.TemplateResponse("admin/instructors_list.html", context)

# CREATE (Show Add Instructor Form)
# Final URL: /admin/instructors/add
@router.get("/add", response_class=HTMLResponse, name="admin_manage_instructor_add_form")
async def add_instructor_form_for_admin(
    request: Request,
    db: Session = Depends(database.get_db), # Need db to fetch departments
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    default_pwd_display = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
    departments = department_service.get_all_departments(db) # Fetch departments for dropdown
    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "instructor": None,
        "departments": departments, # Pass departments to template
        "page_title": "Add New Instructor",
        "default_password_info": default_pwd_display
    }
    return templates.TemplateResponse("admin/instructor_form.html", context)

# CREATE (Process Add Instructor Form)
# Final URL: /admin/instructors/add
@router.post("/add", response_class=RedirectResponse, name="admin_manage_instructor_add")
async def add_instructor_by_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields matching instructor_form.html
    name: str = Form(...),
    email: str = Form(...), # User email
    username: str = Form(...), # User username
    qualification: Optional[str] = Form(None),
    department_id: Optional[int] = Form(None), # Get department ID from form
    phone: Optional[str] = Form(None)
):
    default_password = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
    try:
        new_instructor = instructor_service.create_instructor_with_user(
            db=db, name=name, email=email, username=username, raw_password=default_password,
            qualification=qualification, department_id=department_id, phone=phone
        )
        logger.info(f"Admin {current_user.username} created instructor {new_instructor.id} (User: {new_instructor.user.username})")
        return RedirectResponse(url=request.url_for('admin_manage_instructors_list'), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch errors like duplicate user or invalid department
        logger.warning(f"Admin {current_user.username} failed to add instructor: {e}")
        departments = department_service.get_all_departments(db) # Re-fetch departments for form
        default_pwd_display = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
        context = {
            "request": request, "user": current_user, "UserRole": UserRole, "instructor": None,
            "departments": departments, "page_title": "Add New Instructor", "error": str(e),
            "form_data": await request.form(), "default_password_info": default_pwd_display
        }
        return templates.TemplateResponse("admin/instructor_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error adding instructor: {e}", exc_info=True)
        departments = department_service.get_all_departments(db) # Re-fetch departments
        default_pwd_display = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
        context = {
            "request": request, "user": current_user, "UserRole": UserRole, "instructor": None,
            "departments": departments, "page_title": "Add New Instructor",
            "error": "An unexpected error occurred.", "form_data": await request.form(),
             "default_password_info": default_pwd_display
        }
        return templates.TemplateResponse("admin/instructor_form.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# UPDATE (Show Edit Instructor Form)
# Final URL: /admin/instructors/{instructor_id}/edit
@router.get("/{instructor_id}/edit", response_class=HTMLResponse, name="admin_manage_instructor_edit_form")
async def edit_instructor_form_for_admin(
    instructor_id: int,
    request: Request,
    db: Session = Depends(database.get_db), # Need db for instructor and departments
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    instructor = instructor_service.get_instructor_by_id_with_user(db, instructor_id=instructor_id)
    if not instructor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")
    departments = department_service.get_all_departments(db) # Fetch departments for dropdown
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "instructor": instructor, # Pass existing instructor data
        "departments": departments, # Pass departments
        "page_title": f"Edit Instructor: {instructor.name}"
    }
    return templates.TemplateResponse("admin/instructor_form.html", context)

# UPDATE (Process Edit Instructor Form)
# Final URL: /admin/instructors/{instructor_id}/edit
@router.post("/{instructor_id}/edit", response_class=RedirectResponse, name="admin_manage_instructor_edit")
async def edit_instructor_by_admin(
    instructor_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields
    name: str = Form(...),
    email: str = Form(...), # User email
    qualification: Optional[str] = Form(None),
    department_id: Optional[int] = Form(None),
    phone: Optional[str] = Form(None)
):
    instructor_to_update = instructor_service.get_instructor_by_id_with_user(db, instructor_id=instructor_id)
    if not instructor_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    update_data = {
        "name": name,
        "qualification": qualification,
        "department_id": department_id,
        "phone": phone,
        "user_email": email
    }
    try:
        updated_instructor = instructor_service.update_instructor_and_user(
            db=db, instructor_id=instructor_id, update_data=update_data
        )
        logger.info(f"Admin {current_user.username} updated instructor {instructor_id}")
        return RedirectResponse(url=request.url_for('admin_manage_instructors_list'), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch errors like duplicate email or invalid dept
        logger.warning(f"Admin {current_user.username} failed to update instructor {instructor_id}: {e}")
        departments = department_service.get_all_departments(db) # Re-fetch departments
        context = {
            "request": request, "user": current_user, "UserRole": UserRole,
            "instructor": instructor_to_update, # Pass existing data back
            "departments": departments,
            "page_title": f"Edit Instructor: {instructor_to_update.name}",
            "error": str(e),
            "form_data": await request.form() # Re-populate form
        }
        return templates.TemplateResponse("admin/instructor_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error updating instructor {instructor_id}: {e}", exc_info=True)
        departments = department_service.get_all_departments(db) # Re-fetch departments
        context = {
            "request": request, "user": current_user, "UserRole": UserRole,
            "instructor": instructor_to_update, "departments": departments,
            "page_title": f"Edit Instructor: {instructor_to_update.name}",
            "error": "An unexpected error occurred.", "form_data": await request.form()
        }
        return templates.TemplateResponse("admin/instructor_form.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# DELETE Instructor
# Final URL: /admin/instructors/{instructor_id}/delete
@router.post("/{instructor_id}/delete", response_class=RedirectResponse, name="admin_manage_instructor_delete")
async def delete_instructor_by_admin(
    instructor_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    success = instructor_service.delete_instructor_and_user(db=db, instructor_id=instructor_id)
    if not success:
        logger.warning(f"Admin {current_user.username} attempted delete non-existent instructor {instructor_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found or could not be deleted")

    logger.info(f"Admin {current_user.username} deleted instructor {instructor_id}")
    return RedirectResponse(url=request.url_for('admin_manage_instructors_list'), status_code=status.HTTP_303_SEE_OTHER)

@router.get("/dashboard", response_class=HTMLResponse, name="instructor_dashboard")
async def get_instructor_dashboard(
    request: Request,
    db: Session = Depends(database.get_db),
    # Use the dependency to ensure user is a logged-in instructor
    current_user: models.User = Depends(auth_service.get_current_active_instructor)
):
    """Displays the dashboard for the logged-in instructor."""

    instructor_profile = current_user.instructor_profile # Assumes relationship loading works
    if not instructor_profile:
         logger.error(f"Instructor profile not found for user ID {current_user.id}")
         pass # Handle error as appropriate

    # Example: Fetch courses the instructor is scheduled to teach
    # scheduled_courses = []
    # if instructor_profile:
    #    schedules = db.query(models.Schedule).options(
    #        joinedload(models.Schedule.course)
    #    ).filter(models.Schedule.instructor_id == instructor_profile.id).distinct(models.Schedule.course_id).all()
    #    scheduled_courses = [s.course for s in schedules if s.course]

    context = {
        "request": request,
        "user": current_user,
        "instructor_profile": instructor_profile,
        "UserRole": UserRole,
        "page_title": "Instructor Dashboard",
        # Add fetched data:
        # "teaching_courses": scheduled_courses,
    }
    # Render a template specific to the instructor dashboard
    return templates.TemplateResponse("instructor/instructor_dashboard.html", context)