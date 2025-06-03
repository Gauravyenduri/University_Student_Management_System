# app/routes/complaint.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import urllib.parse
import json

# Local imports
from app import database, models
from app.services import auth_service, complaint_service, student_service # Need student service for filter
from app.models import UserRole, ComplaintStatus # Import models/enums needed

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/complaints IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Student Complaints ===

# GET: List all complaints (with filters)
@router.get("/", response_class=HTMLResponse, name="admin_manage_complaints")
async def list_complaints_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Admin Auth
    filter_status = Query(None),
    filter_student_id = Query(None),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of all student complaints for admin view."""
    logger.info(f"Admin {current_user.username} accessing complaints list. Filters: status={filter_status}, student={filter_student_id}")
    try:
        complaints = complaint_service.admin_get_all_complaints(db, status=filter_status, student_id=filter_student_id)
        all_students = student_service.get_all_students(db) # For filter dropdown
    except Exception as e:
        logger.error(f"Failed to fetch complaints/students: {e}", exc_info=True)
        complaints = []; all_students = []
        toast_error = toast_error or "Failed to load complaint data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "complaints": complaints,
        "all_students": all_students, # For student filter dropdown
        "complaint_statuses": [status.name for status in ComplaintStatus], # Pass status NAMES
        "current_filter_status": filter_status,
        "current_filter_student_id": filter_student_id,
        "page_title": "Manage Student Complaints",
        "toast_error": toast_error, "toast_success": toast_success
    }
    # New template path
    return templates.TemplateResponse("admin/manage_complaints.html", context)


# POST: Admin updates status and resolution for a complaint
@router.post("/{complaint_id}/update", response_class=RedirectResponse, name="admin_update_complaint")
async def update_complaint_by_admin(
    request: Request,
    complaint_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Admin Auth
    # Form fields from admin modal/form
    new_status: str = Form(...), # Expecting status NAME (e.g., "RESOLVED")
    resolution_note: Optional[str] = Form(None)
):
    """Handles admin updates to complaint status and resolution."""
    # Redirect back to the list page, potentially preserving filters
    redirect_url = request.url_for('admin_manage_complaints')
    # TODO: Persist filters through redirect using query params if desired
    # query_params = list(request.query_params.items()) # Basic way, might need cleaning
    # redirect_url += "?" + urllib.parse.urlencode(query_params)

    logger.info(f"Admin {current_user.username} attempting update on complaint {complaint_id} to status {new_status}")
    try:
        updated_complaint = complaint_service.admin_update_complaint(
            db,
            complaint_id=complaint_id,
            new_status_str=new_status,
            resolution_note=resolution_note
        )
        if updated_complaint is None: raise ValueError("Complaint not found.")

        toast_msg = urllib.parse.quote(f"Complaint #{complaint_id} updated successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating complaint: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating complaint {complaint_id} by admin: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# POST: Admin deletes a complaint record (use with caution)
@router.post("/{complaint_id}/admin-delete", response_class=JSONResponse, name="admin_delete_complaint")
async def delete_complaint_by_admin(
    complaint_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Admin Auth
):
    """Handles deletion of any complaint record by an admin via fetch."""
    logger.info(f"Admin {current_user.username} attempting delete complaint {complaint_id}.")
    try:
        success = complaint_service.admin_delete_complaint(db, complaint_id)
        if not success: raise ValueError("Complaint not found.")
        return JSONResponse(content={"success": True, "message": "Complaint deleted successfully."})
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Admin error deleting complaint {complaint_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})