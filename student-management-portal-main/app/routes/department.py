# app/routes/department.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query # Add Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import urllib.parse # To encode error messages in URL
import json
# Local imports
from app import database, models
from app.services import auth_service, department_service, instructor_service # Need all three
from app.models import UserRole, Department

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Departments ===

# READ (List Departments) - Now also displays errors and provides data for modal
# Final URL: /admin/departments/
@router.get("/", response_class=HTMLResponse, name="admin_manage_departments_list")
async def list_departments_for_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    error: Optional[str] = Query(None),
    success: Optional[str] = Query(None)
):
    departments = department_service.get_all_departments(db)
    all_instructors = instructor_service.get_all_instructors(db)
    instructors = instructor_service.get_all_instructors(db) # Fetch instructors
    instructors_data_for_json = [{"id": i.id, "name": i.name} for i in instructors] # Prepare list of dicts
    instructors_json = json.dumps(instructors_data_for_json) # Create JSON string
    # --- Prepare data for Alpine.js ---

    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "departments": departments,
        # Pass the JSON STRINGS to the template
        "instructors_json": instructors_json,
        # Keep original instructor list if needed elsewhere in template
        "instructors": all_instructors,
        "page_title": "Manage Departments",
        "error_message": error,
        "success_message": success
    }
    return templates.TemplateResponse("admin/departments_list.html", context)


# --- REMOVED ---
# GET /add (Show Add Department Form) - No longer needed

# CREATE (Process Add Department Form)
# Final URL: /admin/departments/add
@router.post("/add", response_class=RedirectResponse, name="admin_manage_department_add")
async def add_department_by_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    name: str = Form(...),
):
    redirect_url = request.url_for('admin_manage_departments_list')
    try:
        new_department = department_service.create_department(db=db, name=name)
        logger.info(f"Admin {current_user.username} created department {new_department.id} ('{new_department.name}')")
        # Redirect with success message
        success_msg = urllib.parse.quote(f"Department '{new_department.name}' created successfully.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch errors like duplicate name
        logger.warning(f"Admin {current_user.username} failed to add department: {e}")
        # Redirect back to list with error message
        error_msg = urllib.parse.quote(str(e)) # URL-encode the error message
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error adding department: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while adding the department.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)


# --- REMOVED ---
# GET /{department_id}/edit (Show Edit Department Form) - No longer needed


# UPDATE (Process Edit Department Form)
# Final URL: /admin/departments/{department_id}/edit
@router.post("/{department_id}/edit", response_class=RedirectResponse, name="admin_manage_department_edit")
async def edit_department_by_admin(
    department_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    name: str = Form(...),
    head_of_department_id: Optional[str] = Form(None) # Comes from modal form
):
    redirect_url = request.url_for('admin_manage_departments_list')
    hod_id_int: Optional[int] = None
    if head_of_department_id and head_of_department_id.isdigit():
        hod_id_int = int(head_of_department_id)

    update_data = { "name": name, "head_of_department_id": hod_id_int }

    try:
        updated_department = department_service.update_department(
            db=db, department_id=department_id, update_data=update_data
        )
        if updated_department is None:
             raise ValueError("Department not found.") # Treat not found as ValueError for redirection

        logger.info(f"Admin {current_user.username} updated department {department_id}")
        success_msg = urllib.parse.quote(f"Department '{updated_department.name}' updated successfully.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e: # Catch errors like duplicate name, invalid HoD, not found
        logger.warning(f"Admin {current_user.username} failed to update department {department_id}: {e}")
        error_msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error updating department {department_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while updating the department.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)

# DELETE Department
# Final URL: /admin/departments/{department_id}/delete
@router.post("/{department_id}/delete", response_class=RedirectResponse, name="admin_manage_department_delete")
async def delete_department_by_admin(
    department_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    redirect_url = request.url_for('admin_manage_departments_list')
    dept_name_temp = f"ID {department_id}" # Fallback name
    try:
        # Optional: Get name before deleting for success message
        dept = department_service.get_department_by_id(db, department_id)
        if dept: dept_name_temp = dept.name

        success = department_service.delete_department(db=db, department_id=department_id)
        if not success: # Should ideally not happen if service raises ValueError
             raise ValueError("Department not found.")

        logger.info(f"Admin {current_user.username} deleted department {department_id}")
        success_msg = urllib.parse.quote(f"Department '{dept_name_temp}' deleted successfully.")
        return RedirectResponse(url=f"{redirect_url}?success={success_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch "cannot delete" or "not found" errors
         logger.warning(f"Admin {current_user.username} failed to delete department {department_id}: {e}")
         error_msg = urllib.parse.quote(str(e))
         return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error deleting department {department_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while deleting the department.")
        return RedirectResponse(url=f"{redirect_url}?error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)