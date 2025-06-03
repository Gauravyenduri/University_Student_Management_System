# app/routes/alumni.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import urllib.parse
import json

# Local imports
from app import database, models
from app.services import auth_service, alumni_service, student_service # Need student service
from app.models import UserRole # Import models needed

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/alumni IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Alumni Records ===

# READ (List Alumni)
@router.get("/", response_class=HTMLResponse, name="admin_manage_alumni")
async def list_alumni_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Admin Auth
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of all alumni records for admin view."""
    logger.info(f"Admin {current_user.username} accessing alumni list.")
    try:
        alumni_list = alumni_service.get_all_alumni(db)
        # Get students *who don't already have an alumni record* for the Add modal dropdown
        existing_alumni_student_ids = {a.student_id for a in alumni_list}
        all_students = student_service.get_all_students(db)
        available_students = [s for s in all_students if s.id not in existing_alumni_student_ids]
        students_json = json.dumps([{"id": s.id, "name": s.name} for s in available_students])

    except Exception as e:
        logger.error(f"Failed to fetch alumni/students: {e}", exc_info=True)
        alumni_list = []; students_json = "[]"
        toast_error = toast_error or "Failed to load alumni data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "alumni_list": alumni_list,
        "students_json": students_json, # For Add modal
        "page_title": "Manage Alumni Records",
        "toast_error": toast_error, "toast_success": toast_success
    }
    # New template path needed
    return templates.TemplateResponse("admin/manage_alumni.html", context)


# CREATE Alumni Record (Process Add Form)
@router.post("/add", response_class=RedirectResponse, name="admin_add_alumni")
async def add_alumni_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    # Form fields from modal
    student_id_str: str = Form(...),
    graduation_year_str: Optional[str] = Form(None),
    current_job: Optional[str] = Form(None),
    current_employer: Optional[str] = Form(None),
    contact_info: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_alumni')
    logger.info(f"Admin {current_user.username} attempting to add alumni record.")
    try:
        student_id = int(student_id_str)
        grad_year = int(graduation_year_str) if graduation_year_str and graduation_year_str.isdigit() else None

        new_alumni = alumni_service.create_alumni_record(
            db, student_id=student_id, graduation_year=grad_year,
            current_job=current_job, current_employer=current_employer, contact_info=contact_info
        )
        toast_msg = urllib.parse.quote(f"Alumni record created for student ID {student_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding alumni: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding alumni: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# UPDATE Alumni Record (Process Edit Form)
@router.post("/{alumni_id}/edit", response_class=RedirectResponse, name="admin_edit_alumni")
async def edit_alumni_by_admin(
    alumni_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
     # Form fields from modal (student_id not editable)
    graduation_year_str: Optional[str] = Form(None),
    current_job: Optional[str] = Form(None),
    current_employer: Optional[str] = Form(None),
    contact_info: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_alumni')
    update_data = {}
    try:
        # Prepare update data (only include fields passed from form)
        update_data['graduation_year'] = int(graduation_year_str) if graduation_year_str and graduation_year_str.isdigit() else None
        if current_job is not None: update_data['current_job'] = current_job.strip() if current_job else None
        if current_employer is not None: update_data['current_employer'] = current_employer.strip() if current_employer else None
        if contact_info is not None: update_data['contact_info'] = contact_info.strip() if contact_info else None

        updated_alumni = alumni_service.update_alumni_record(db, alumni_id, update_data)
        if updated_alumni is None: raise ValueError("Alumni record not found.")

        toast_msg = urllib.parse.quote(f"Alumni record {alumni_id} updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating alumni: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating alumni {alumni_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# DELETE Alumni Record
@router.post("/{alumni_id}/delete", response_class=JSONResponse, name="admin_delete_alumni")
async def delete_alumni_by_admin(
    alumni_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    """Handles deletion of an alumni record by an admin via fetch."""
    logger.info(f"Admin {current_user.username} attempting delete alumni record {alumni_id}.")
    try:
        success = alumni_service.delete_alumni_record(db, alumni_id)
        if not success: raise ValueError("Alumni record not found.")
        return JSONResponse(content={"success": True, "message": "Alumni record deleted successfully."})
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting alumni record {alumni_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})