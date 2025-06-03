# app/routes/student.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os
from datetime import date
import urllib.parse # For encoding toast messages
from app.services import auth_service, enrollment_service, department_service # Import enrollment and department service

# Local imports
from app import database, models
from app.services import auth_service, student_service # student_service needed here now
from app.models import UserRole, User, Student, Department # Import Department

logger = logging.getLogger(__name__)

# THIS ROUTER WILL BE MOUNTED WITH A PREFIX like /admin/students in main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Students ===
# All routes below require admin privileges

# READ (List Students)
# Note: The final URL will be /admin/students/ because of the prefix in main.py
@router.get("/", response_class=HTMLResponse, name="admin_manage_students_list")
async def list_students_for_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    students = student_service.get_all_students(db)
    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "students": students,
        "page_title": "Manage Students"
    }
    # Render the template from the admin section's perspective
    return templates.TemplateResponse("admin/students_list.html", context)

# CREATE (Show Add Student Form)
# Final URL: /admin/students/add
@router.get("/add", response_class=HTMLResponse, name="admin_manage_student_add_form")
async def add_student_form_for_admin(
    request: Request,
    db: Session = Depends(database.get_db), # Need db session to fetch departments
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    default_pwd_display = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
    departments = department_service.get_all_departments(db) # Fetch departments

    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "student": None,
        "departments": departments, # Add departments to context
        "page_title": "Add New Student",
        "default_password_info": default_pwd_display
    }
    return templates.TemplateResponse("admin/student_form.html", context)

# CREATE (Process Add Student Form)
# Final URL: /admin/students/add
@router.post("/add", response_class=RedirectResponse, name="admin_manage_student_add")
async def add_student_by_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    dob: Optional[date] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    department_id = Form(None) # Add department_id form field
):
    default_password = os.getenv("DEFAULT_NEW_USER_PASSWORD", "12345")
    try:
        new_student = student_service.create_student_with_user(
            db=db, name=name, email=email, username=username, raw_password=default_password,
            dob=dob, phone=phone, address=address, department_id=department_id # Pass department_id
        )
        logger.info(f"Admin {current_user.username} created student {new_student.id} (User: {new_student.user.username}, Dept: {department_id})")
        # Redirect to the student list
        return RedirectResponse(url=request.url_for('admin_manage_students_list'), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        logger.warning(f"Admin {current_user.username} failed to add student: {e}")
        departments = department_service.get_all_departments(db) # Fetch departments for error page
        context = {
            "request": request, "user": current_user, "UserRole": UserRole, "student": None,
            "departments": departments, "page_title": "Add New Student", "error": str(e),
            "form_data": await request.form()
        }
        return templates.TemplateResponse("admin/student_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error adding student: {e}", exc_info=True)
        departments = department_service.get_all_departments(db) # Fetch departments for error page
        context = {
            "request": request, "user": current_user, "UserRole": UserRole, "student": None,
            "departments": departments, "page_title": "Add New Student", "error": "An unexpected error occurred.",
            "form_data": await request.form()
        }
        return templates.TemplateResponse("admin/student_form.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# UPDATE (Show Edit Student Form)
# Final URL: /admin/students/{student_id}/edit
@router.get("/{student_id}/edit", response_class=HTMLResponse, name="admin_manage_student_edit_form")
async def edit_student_form_for_admin(
    student_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    student = student_service.get_student_by_id_with_user(db, student_id=student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    departments = department_service.get_all_departments(db) # Fetch departments
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "student": student, "departments": departments, # Add departments to context
        "page_title": f"Edit Student: {student.name}"
    }
    return templates.TemplateResponse("admin/student_form.html", context)

# UPDATE (Process Edit Student Form)
# Final URL: /admin/students/{student_id}/edit
@router.post("/{student_id}/edit", response_class=RedirectResponse, name="admin_manage_student_edit")
async def edit_student_by_admin(
    student_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    name: str = Form(...),
    email: str = Form(...),
    dob: Optional[date] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    department_id: Optional[int] = Form(None) # Add department_id form field
):
    student_to_update = student_service.get_student_by_id_with_user(db, student_id=student_id)
    if not student_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    update_data = {
        "name": name, "dob": dob, "phone": phone, "address": address,
        "user_email": email, "department_id": department_id # Add department_id to update data
    }
    try:
        updated_student = student_service.update_student_and_user(db=db, student_id=student_id, update_data=update_data)
        logger.info(f"Admin {current_user.username} updated student {student_id} (Dept: {department_id})")
        return RedirectResponse(url=request.url_for('admin_manage_students_list'), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        logger.warning(f"Admin {current_user.username} failed to update student {student_id}: {e}")
        departments = department_service.get_all_departments(db) # Fetch departments for error page
        # Re-fetch student in case some data was partially updated before error
        student_for_form = student_service.get_student_by_id_with_user(db, student_id=student_id) or student_to_update
        context = {
            "request": request, "user": current_user, "UserRole": UserRole,
            "student": student_for_form, "departments": departments,
            "page_title": f"Edit Student: {student_for_form.name}",
            "error": str(e), "form_data": await request.form()
        }
        return templates.TemplateResponse("admin/student_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error updating student {student_id}: {e}", exc_info=True)
        departments = department_service.get_all_departments(db) # Fetch departments for error page
        student_for_form = student_service.get_student_by_id_with_user(db, student_id=student_id) or student_to_update
        context = {
            "request": request, "user": current_user, "UserRole": UserRole,
            "student": student_for_form, "departments": departments,
            "page_title": f"Edit Student: {student_for_form.name}",
            "error": "An unexpected error occurred.", "form_data": await request.form()
        }
        return templates.TemplateResponse("admin/student_form.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# DELETE Student
# Final URL: /admin/students/{student_id}/delete
@router.post("/{student_id}/delete", response_class=RedirectResponse, name="admin_manage_student_delete")
async def delete_student_by_admin(
    student_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    success = student_service.delete_student_and_user(db=db, student_id=student_id)
    if not success:
        logger.warning(f"Admin {current_user.username} attempted delete non-existent student {student_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found or could not be deleted")

    logger.info(f"Admin {current_user.username} deleted student {student_id}")
    return RedirectResponse(url=request.url_for('admin_manage_students_list'), status_code=status.HTTP_303_SEE_OTHER)
