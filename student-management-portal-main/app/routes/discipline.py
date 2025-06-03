# app/routes/discipline.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import urllib.parse
import json
from datetime import date

# Local imports
from app import database, models
from app.services import auth_service, discipline_service, student_service # Need student service
from app.models import UserRole # Import models needed

logger = logging.getLogger(__name__)

# THIS ROUTER COULD BE MOUNTED UNDER /instructor/discipline OR /admin/discipline
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Decide on Auth: Admin or Instructor? Using Instructor for now.
AUTH_DEPENDENCY = auth_service.get_current_active_instructor

# === Instructor Management of Discipline Records ===

# READ (List Records)
@router.get("/", response_class=HTMLResponse, name="manage_discipline_records")
async def list_discipline_records(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(AUTH_DEPENDENCY),
    filter_student_id: Optional[int] = Query(None), # Allow filtering by student
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of discipline records, manageable by authorized staff."""
    logger.info(f"User {current_user.username} accessing discipline records list.")
    try:
        records = discipline_service.get_all_discipline_records(db, student_id=filter_student_id)
        # Get all students for filter dropdown AND for Add modal
        all_students = student_service.get_all_students(db)
        students_json = json.dumps([{"id": s.id, "name": s.name} for s in all_students])

    except Exception as e:
        logger.error(f"Failed to fetch discipline records/students: {e}", exc_info=True)
        records = []; students_json = "[]"; all_students = []
        toast_error = toast_error or "Failed to load discipline data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "discipline_records": records,
        "all_students": all_students, # For filter dropdown
        "students_json": students_json, # For modal dropdown
        "current_filter_student_id": filter_student_id, # Pass back filter value
        "page_title": "Manage Discipline Records",
        "toast_error": toast_error, "toast_success": toast_success
    }
    # Use generic admin path for template for now, adjust if needed
    return templates.TemplateResponse("instructor/discipline_records_list.html", context)


# CREATE Record (Process Add Form)
@router.post("/add", response_class=RedirectResponse, name="add_discipline_record")
async def add_discipline_record(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(AUTH_DEPENDENCY),
    # Form fields from modal
    student_id_str: str = Form(...),
    incident_date_str: str = Form(...),
    incident_description: str = Form(...),
    action_taken: Optional[str] = Form(None)
):
    redirect_url = request.url_for('manage_discipline_records') # Redirect back to list
    logger.info(f"User {current_user.username} attempting to add discipline record.")
    try:
        student_id = int(student_id_str)
        incident_date = date.fromisoformat(incident_date_str)
        if not incident_description or not incident_description.strip():
            raise ValueError("Incident description is required.")

        new_record = discipline_service.create_discipline_record(
            db, student_id=student_id, incident_date=incident_date,
            incident_description=incident_description, action_taken=action_taken
        )
        toast_msg = urllib.parse.quote(f"Discipline record created for student ID {student_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding record: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding discipline record: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# UPDATE Record (Process Edit Form)
@router.post("/{record_id}/edit", response_class=RedirectResponse, name="edit_discipline_record")
async def edit_discipline_record(
    record_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(AUTH_DEPENDENCY),
     # Form fields from modal (student_id not editable)
    incident_date_str: str = Form(...),
    incident_description: str = Form(...),
    action_taken: Optional[str] = Form(None)
):
    redirect_url = request.url_for('manage_discipline_records')
    update_data = {}
    try:
        # Prepare update data
        update_data['incident_date'] = date.fromisoformat(incident_date_str)
        if not incident_description or not incident_description.strip():
             raise ValueError("Incident description is required.")
        update_data['incident_description'] = incident_description.strip()
        update_data['action_taken'] = action_taken.strip() if action_taken else None

        updated_record = discipline_service.update_discipline_record(db, record_id, update_data)
        if updated_record is None: raise ValueError("Discipline record not found.")

        toast_msg = urllib.parse.quote(f"Discipline record {record_id} updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating record: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating discipline record {record_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# DELETE Record
@router.post("/{record_id}/delete", response_class=JSONResponse, name="delete_discipline_record")
async def delete_discipline_record(
    record_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(AUTH_DEPENDENCY)
):
    """Handles deletion of a discipline record via fetch."""
    logger.info(f"User {current_user.username} attempting delete discipline record {record_id}.")
    try:
        success = discipline_service.delete_discipline_record(db, record_id)
        if not success: raise ValueError("Record not found.")
        return JSONResponse(content={"success": True, "message": "Discipline record deleted."})
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting discipline record {record_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})