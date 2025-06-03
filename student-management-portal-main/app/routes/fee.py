# app/routes/fee.py

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
from app.services import auth_service, fee_service, student_service # student_service needed for Add modal
from app.models import UserRole, FeePayment, PaymentStatus # Import specific models/enums

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/fees IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Fees ===

# READ (Admin List Fees)
@router.get("/", response_class=HTMLResponse, name="admin_manage_fees_list")
async def list_fees_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require Admin
    filter_status  = Query(None),
    search_student = Query(None), # Placeholder for search value
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of all fee records for admin view, with filters."""
    logger.info(f"Admin {current_user.username} accessing fee list. Filters: status={filter_status}, search={search_student}")

    # Fetch students ONLY for the "Add Fee Record" modal dropdown
    students = student_service.get_all_students(db)
    students_json = json.dumps([{"id": s.id, "name": s.name} for s in students])

    # Fetch fee records - Service function should handle filtering/searching
    # TODO: Implement search_student logic in fee_service.get_all_fee_payments
    fee_records = fee_service.get_all_fee_payments(db, status=filter_status, search_student=search_student)
    logger.debug(f"Found {len(fee_records)} fee records matching filters.")

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"

    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "fee_records": fee_records,
        "students_json": students_json, # For Add modal student dropdown
        "all_students": students,
        "payment_statuses": [status.name for status in PaymentStatus], # Pass NAMES for filter/modal dropdowns
        "current_filter_status": filter_status,
        "current_search_student": search_student,
        "page_title": "Manage Fee Payments",
        "toast_error": toast_error,
        "toast_success": toast_success
    }
    return templates.TemplateResponse("admin/fees_list.html", context)


# CREATE (Admin Adds a New Fee Demand/Record)
@router.post("/add", response_class=RedirectResponse, name="admin_manage_fee_add")
async def add_fee_record_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require Admin
    # Form fields from Add mode in modal
    student_id_str: str = Form(...),
    amount_str: str = Form(...),
    due_date_str: str = Form(...),
    description: Optional[str] = Form(None)
):
    """Handles creation of a new fee demand record by an admin."""
    redirect_url = request.url_for('admin_manage_fees_list')
    logger.info(f"Admin {current_user.username} attempting to add fee record.")
    try:
        # Convert and validate basic input
        student_id = int(student_id_str)
        amount = float(amount_str)
        due_date = date.fromisoformat(due_date_str)
        if amount <= 0: raise ValueError("Amount due must be positive.")

        # Call service to create the PENDING record
        new_fee = fee_service.create_fee_record(db, student_id, amount, due_date, description)
        logger.info(f"Fee record {new_fee.id} created for student {student_id} by admin {current_user.username}.")
        toast_msg = urllib.parse.quote(f"Fee record created for student ID {student_id}.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        logger.warning(f"Admin add fee record failed: {e}")
        toast_msg = urllib.parse.quote(f"Error creating fee record: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding fee record: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred while creating the fee record.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# UPDATE (Admin Edits Fee DEMAND Details - e.g., amount due, due date, description, cancel)
@router.post("/{payment_id}/edit", response_class=RedirectResponse, name="admin_manage_fee_edit")
async def edit_fee_details_by_admin(
    payment_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require Admin
    # Form fields from Edit mode in modal (Demand details + Cancel status)
    description: Optional[str] = Form(None),
    amount_str: str = Form(...),        # Amount DUE
    due_date_str: str = Form(...),      # Due Date
    status_str: Optional[str] = Form(None) # Should only be 'CANCELLED' if sent
):
    """Handles admin updates to the details of a fee demand record."""
    redirect_url = request.url_for('admin_manage_fees_list')
    logger.info(f"Admin {current_user.username} attempting to edit fee record {payment_id} details.")
    update_data: Dict[str, Any] = {}
    try:
        # --- Prepare Update Data (Validate/Convert Admin Editable Fields) ---
        if description is not None: # Allow empty description
            update_data['description'] = description.strip() if description else None

        # Amount DUE
        if amount_str and amount_str.strip():
            try:
                amount_due = float(amount_str)
                if amount_due <= 0: raise ValueError("Amount due must be positive.")
                update_data['amount'] = amount_due
            except ValueError:
                raise ValueError("Invalid Amount Due format.")
        else:
            raise ValueError("Amount Due is required.") # Make it required

        # Due Date
        if due_date_str and due_date_str.strip():
             try: update_data['date'] = date.fromisoformat(due_date_str)
             except ValueError: raise ValueError("Invalid Due Date format (YYYY-MM-DD).")
        else:
             raise ValueError("Due Date is required.") # Make it required

        # Status (Admin can only Cancel via this form)
        if status_str and status_str.strip():
            if status_str.upper() == models.PaymentStatus.CANCELLED.name:
                 update_data['status'] = models.PaymentStatus.CANCELLED.name
            else:
                 # Don't allow setting other statuses here; log maybe?
                 logger.warning(f"Admin attempted to set invalid status '{status_str}' via edit form for fee {payment_id}. Ignoring.")
                 # raise ValueError("Admin can only explicitly set status to CANCELLED.")

        logger.debug(f"Prepared update data for fee {payment_id}: {update_data}")

        # --- Call Service ---
        updated_fee = fee_service.update_fee_record_details(db, payment_id, update_data)
        if updated_fee is None: raise ValueError("Fee record not found.") # Service should return object or raise

        logger.info(f"Fee record {payment_id} details updated by admin {current_user.username}.")
        toast_msg = urllib.parse.quote(f"Fee record {payment_id} details updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        logger.warning(f"Admin edit fee details failed for ID {payment_id}: {e}")
        toast_msg = urllib.parse.quote(f"Error updating fee details: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating fee details {payment_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred while updating details.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status_code=status.HTTP_303_SEE_OTHER)


# DELETE Fee Record (Admin Action)
@router.post("/{payment_id}/delete", response_class=JSONResponse, name="admin_manage_fee_delete")
async def delete_fee_record_by_admin(
    payment_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require Admin
):
    """Handles deletion of a fee record by an admin."""
    logger.info(f"Admin {current_user.username} attempting to delete fee record {payment_id}.")
    try:
        success = fee_service.delete_fee_record(db, payment_id)
        # Service should raise ValueError if not found or cannot delete
        logger.info(f"Fee record {payment_id} deleted by admin {current_user.username}.")
        return JSONResponse(content={"success": True, "message": "Fee record deleted successfully."})
    except ValueError as e:
        logger.warning(f"Admin delete fee record failed for ID {payment_id}: {e}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting fee record {payment_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "An unexpected error occurred."})