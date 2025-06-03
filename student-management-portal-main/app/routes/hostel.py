# app/routes/hostel.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import urllib.parse
import json
from datetime import date # Keep date import for date fields if still used elsewhere

# Local imports
from app import database, models
from app.services import auth_service, hostel_service, student_service
from app.models import UserRole

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/hostel IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Hostel Assignments ===

# READ (List Hostel Assignments)
@router.get("/", response_class=HTMLResponse, name="admin_manage_hostels")
async def manage_hostel_assignments_page(
    request: Request, response: Response, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    toast_error: Optional[str] = Query(None), toast_success: Optional[str] = Query(None)
):
    """Displays page for admin to manage student hostel assignments."""
    logger.info(f"Admin {current_user.username} accessing hostel assignments list.")
    try:
        assignments = hostel_service.get_all_hostel_assignments(db)
        students_json = json.dumps([{"id": s.id, "name": s.name} for s in student_service.get_all_students(db)])
        hostel_names_json = json.dumps(hostel_service.HOSTEL_NAMES)
    except Exception as e: logger.error(f"Error fetching hostel data: {e}", exc_info=True); assignments = []; students_json = "[]"; hostel_names_json = "[]"; toast_error = toast_error or "Failed to load hostel data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate";
    context = {
        "request": request, "user": current_user, "UserRole": UserRole, "hostel_assignments": assignments,
        "students_json": students_json, "hostel_names_json": hostel_names_json,
        "page_title": "Manage Hostel Assignments", "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("admin/manage_hostels.html", context)


# CREATE Hostel Assignment
@router.post("/add", response_class=RedirectResponse, name="admin_assign_hostel")
async def assign_hostel_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    student_id_str: str = Form(...),
    hostel_name: str = Form(...),
    room_number: str = Form(...),
    fees_str: Optional[str] = Form(None),
    # REMOVED: check_in_date_str: Optional[str] = Form(None)  # Removed check-in date
    # REMOVED: return_date_str: Optional[str] = Form(None)   # Removed return date
):
    redirect_url = request.url_for('admin_manage_hostels')
    logger.info(f"Admin {current_user.username} attempting to add hostel assignment.")
    try:
        student_id = int(student_id_str)
        fees = float(fees_str) if fees_str and fees_str.strip() else None
        # REMOVED: check_in_date = date.fromisoformat(check_in_date_str) if check_in_date_str else None # Removed

        new_assignment = hostel_service.assign_hostel(
            db, student_id=student_id, hostel_name=hostel_name, room_number=room_number.strip(),
            fees=fees # Removed: , check_in_date=check_in_date # Removed
        )
        toast_msg = urllib.parse.quote(f"Hostel assigned successfully to student ID {student_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding assignment: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding hostel assignment: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# UPDATE Hostel Assignment
@router.post("/{assignment_id}/edit", response_class=RedirectResponse, name="admin_edit_hostel_assignment")
async def edit_hostel_assignment_by_admin(
    assignment_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    # Form fields - Removed date fields
    hostel_name: str = Form(...), room_number: str = Form(...), fees_str: Optional[str] = Form(None),
    # REMOVED: check_in_date_str: Optional[str] = Form(None), # Removed
    # REMOVED: check_out_date_str: Optional[str] = Form(None) # Removed
):
    redirect_url = request.url_for('admin_manage_hostels')
    update_data = {}
    try:
        update_data['hostel_name'] = hostel_name
        update_data['room_number'] = room_number.strip()
        update_data['fees'] = float(fees_str) if fees_str and fees_str.strip() else None
        # Removed: update_data['check_in_date'] = date.fromisoformat(check_in_date_str) if check_in_date_str else None # Removed
        # Removed: update_data['check_out_date'] = date.fromisoformat(check_out_date_str) if check_out_date_str else None # Removed

        updated_record = hostel_service.update_hostel_assignment(db, assignment_id, update_data)
        if updated_record is None: raise ValueError("Assignment record not found.")

        toast_msg = urllib.parse.quote(f"Hostel assignment {assignment_id} updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating assignment: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating assignment {assignment_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# DELETE Hostel Assignment
@router.post("/{assignment_id}/delete", response_class=JSONResponse, name="admin_delete_hostel_assignment")
async def delete_hostel_assignment_by_admin(
    assignment_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    """Handles deletion of a hostel assignment record by an admin via fetch."""
    logger.info(f"Admin {current_user.username} attempting delete hostel assignment {assignment_id}.")
    try:
        success = hostel_service.delete_hostel_assignment(db, assignment_id)
        if not success: raise ValueError("Assignment record not found.")
        return JSONResponse(content={"success": True, "message": "Hostel assignment deleted."})
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting hostel assignment {assignment_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})