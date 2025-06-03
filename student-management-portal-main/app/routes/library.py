# app/routes/library.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any # Added Dict, Any
import logging
import urllib.parse
import json
from datetime import date

# Local imports
from app import database, models
from app.services import auth_service, library_service, student_service # Need student service
from app.models import UserRole # Import models needed

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/library IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Library Borrowing Records ===

# READ (List Library Records)
@router.get("/records", response_class=HTMLResponse, name="admin_manage_library_records") # Changed route name
async def list_library_records_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of all library borrowing records for admin view."""
    logger.info(f"Admin {current_user.username} accessing library records list.")
    try:
        records = library_service.get_all_library_records(db)
        # Fetch students for the 'Add Record' modal dropdown
        students = student_service.get_all_students(db)
        students_json = json.dumps([{"id": s.id, "name": s.name} for s in students])
    except Exception as e:
        logger.error(f"Failed to fetch library records or students: {e}", exc_info=True)
        records = []
        students_json = "[]"
        toast_error = toast_error or "Failed to load library data."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "library_records": records, # Pass the borrowing records
        "students_json": students_json, # Pass students for modal
        "page_title": "Manage Library Records",
        "toast_error": toast_error, "toast_success": toast_success
    }
    # Use a new template name
    return templates.TemplateResponse("admin/library_records_list.html", context)


# CREATE Borrowing Record (Process Add Form)
@router.post("/records/add", response_class=RedirectResponse, name="admin_manage_library_record_add")
async def add_library_record_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    # Form fields from modal
    student_id_str: str = Form(...),
    books_borrowed_str: str = Form(...),
    borrowed_date_str: Optional[str] = Form(None),
    return_date_str: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_library_records')
    logger.info(f"Admin {current_user.username} attempting to add library record.")
    try:
        # Convert/validate
        student_id = int(student_id_str)
        books_borrowed = int(books_borrowed_str)
        borrowed_date = date.fromisoformat(borrowed_date_str) if borrowed_date_str else None
        return_date = date.fromisoformat(return_date_str) if return_date_str else None

        new_record = library_service.create_library_record(
            db, student_id=student_id, books_borrowed=books_borrowed,
            borrowed_date=borrowed_date, return_date=return_date
        )
        toast_msg = urllib.parse.quote(f"Library record created for student ID {student_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding record: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding library record: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# UPDATE Borrowing Record (Process Edit Form)
@router.post("/records/{record_id}/edit", response_class=RedirectResponse, name="admin_manage_library_record_edit")
async def edit_library_record_by_admin(
    record_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
     # Form fields from modal
    books_borrowed_str: str = Form(...),
    borrowed_date_str: Optional[str] = Form(None),
    return_date_str: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_library_records')
    update_data = {}
    try:
        # --- Prepare Update Data ---
        update_data['books_borrowed'] = int(books_borrowed_str) # Service validates >= 0
        update_data['borrowed_date'] = date.fromisoformat(borrowed_date_str) if borrowed_date_str else None
        update_data['return_date'] = date.fromisoformat(return_date_str) if return_date_str else None
        # student_id is generally not editable for an existing record

        updated_record = library_service.update_library_record(db, record_id, update_data)
        if updated_record is None: raise ValueError("Library record not found.")

        toast_msg = urllib.parse.quote(f"Library record {record_id} updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating record: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating library record {record_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# DELETE Borrowing Record
@router.post("/records/{record_id}/delete", response_class=JSONResponse, name="admin_manage_library_record_delete")
async def delete_library_record_by_admin(
    record_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    """Handles deletion of a library borrowing record by an admin via fetch."""
    logger.info(f"Admin {current_user.username} attempting delete library record {record_id}.")
    try:
        success = library_service.delete_library_record(db, record_id)
        if not success: raise ValueError("Record not found.")
        return JSONResponse(content={"success": True, "message": "Library record deleted successfully."})
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting library record {record_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "An unexpected error occurred."})