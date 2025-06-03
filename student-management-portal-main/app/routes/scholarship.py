# app/routes/scholarship.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging, urllib.parse, json
from datetime import date

from app import database, models
from app.services import auth_service, scholarship_service, student_service # Need student service
from app.models import UserRole, Scholarship, StudentScholarship

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Scholarship Definitions ===

# READ Definitions
@router.get("/definitions", response_class=HTMLResponse, name="admin_manage_scholarships_list")
async def list_scholarship_defs_for_admin(
    request: Request, response: Response, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    toast_error: Optional[str] = Query(None), toast_success: Optional[str] = Query(None)
):
    definitions = scholarship_service.get_all_scholarship_definitions(db)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "definitions": definitions, "page_title": "Manage Scholarship Definitions",
        "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("admin/scholarships_list.html", context)

# CREATE Definition
@router.post("/definitions/add", response_class=RedirectResponse, name="admin_manage_scholarship_add")
async def add_scholarship_def_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    name: str = Form(...), amount_str: str = Form(...), eligibility: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_scholarships_list')
    try:
        amount = float(amount_str)
        if amount <= 0: raise ValueError("Amount must be positive.")
        new_def = scholarship_service.create_scholarship_definition(db, name, amount, eligibility)
        toast_msg = urllib.parse.quote(f"Scholarship '{new_def.name}' created.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e: logger.error(f"Error adding scholarship def: {e}"); toast_msg = urllib.parse.quote("Unexpected error."); return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

# UPDATE Definition
@router.post("/definitions/{scholarship_id}/edit", response_class=RedirectResponse, name="admin_manage_scholarship_edit")
async def edit_scholarship_def_by_admin(
    scholarship_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    name: str = Form(...), amount_str: str = Form(...), eligibility: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_scholarships_list')
    try:
        amount = float(amount_str)
        if amount <= 0: raise ValueError("Amount must be positive.")
        update_data = {"name": name, "amount": amount, "eligibility": eligibility}
        updated_def = scholarship_service.update_scholarship_definition(db, scholarship_id, update_data)
        if updated_def is None: raise ValueError("Scholarship not found.")
        toast_msg = urllib.parse.quote(f"Scholarship '{updated_def.name}' updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e: toast_msg = urllib.parse.quote(f"Error: {e}"); return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e: logger.error(f"Error updating scholarship def {scholarship_id}: {e}"); toast_msg = urllib.parse.quote("Unexpected error."); return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)

# DELETE Definition
@router.post("/definitions/{scholarship_id}/delete", response_class=JSONResponse, name="admin_manage_scholarship_delete")
async def delete_scholarship_def_by_admin(
    scholarship_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    try:
        success = scholarship_service.delete_scholarship_definition(db, scholarship_id)
        if not success: raise ValueError("Scholarship not found.")
        return JSONResponse(content={"success": True, "message": "Scholarship definition deleted."})
    except ValueError as e: return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e: logger.error(f"Error deleting scholarship def {scholarship_id}: {e}"); return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})


# === Admin Management of Scholarship Assignments ===

# READ Assignments
@router.get("/assignments", response_class=HTMLResponse, name="admin_manage_scholarship_assignments_list")
async def list_scholarship_assignments_for_admin(
    request: Request, response: Response, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    toast_error: Optional[str] = Query(None), toast_success: Optional[str] = Query(None)
):
    assignments = scholarship_service.get_all_scholarship_assignments(db)
    # Data for modal
    students = student_service.get_all_students(db)
    scholarships = scholarship_service.get_all_scholarship_definitions(db)
    students_json = json.dumps([{"id": s.id, "name": s.name} for s in students])
    scholarships_json = json.dumps([{"id": s.id, "name": s.name} for s in scholarships])

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "assignments": assignments,
        "students_json": students_json,
        "scholarships_json": scholarships_json,
        "page_title": "Manage Scholarship Assignments",
        "toast_error": toast_error, "toast_success": toast_success
    }
    return templates.TemplateResponse("admin/scholarship_assignments_list.html", context)

# CREATE Assignment
@router.post("/assignments/add", response_class=RedirectResponse, name="admin_manage_scholarship_assign")
async def assign_scholarship_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    student_id_str: str = Form(...), scholarship_id_str: str = Form(...), academic_year: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_scholarship_assignments_list')
    try:
        student_id = int(student_id_str); scholarship_id = int(scholarship_id_str)
        new_assign = scholarship_service.assign_scholarship_to_student(db, student_id, scholarship_id, academic_year)
        toast_msg = urllib.parse.quote("Scholarship assigned successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e: toast_msg = urllib.parse.quote(f"Error: {e}"); return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e: logger.error(f"Error assigning scholarship: {e}"); toast_msg = urllib.parse.quote("Unexpected error."); return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# DELETE Assignment (Revoke)
@router.post("/assignments/{assignment_id}/delete", response_class=JSONResponse, name="admin_manage_scholarship_revoke")
async def revoke_scholarship_by_admin(
    assignment_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    try:
        success = scholarship_service.revoke_scholarship_assignment(db, assignment_id)
        if not success: raise ValueError("Assignment not found.")
        return JSONResponse(content={"success": True, "message": "Scholarship assignment revoked."})
    except ValueError as e: return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e: logger.error(f"Error revoking scholarship assignment {assignment_id}: {e}"); return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})