# app/routes/classroom.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import urllib.parse
import json # For passing data to template

# Local imports
from app import database, models
from app.services import auth_service, classroom_service # Import classroom service
from app.models import UserRole, Classroom # Import models

logger = logging.getLogger(__name__)

# THIS ROUTER WILL BE MOUNTED WITH A PREFIX like /admin/classrooms in main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Classrooms ===

# READ (List Classrooms)
# Final URL: /admin/classrooms/
@router.get("/", response_class=HTMLResponse, name="admin_manage_classrooms_list")
async def list_classrooms_for_admin(
    request: Request,
    response: Response, # Inject Response for cache headers
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    error: Optional[str] = Query(None),
    success: Optional[str] = Query(None)
):
    classrooms = classroom_service.get_all_classrooms(db)

    # Set cache headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole,
        "classrooms": classrooms,
        "page_title": "Manage Classrooms",
        "error_message": error,
        "success_message": success
    }
    return templates.TemplateResponse("admin/classrooms_list.html", context)

# CREATE (Process Add Classroom Form)
# Final URL: /admin/classrooms/add
@router.post("/add", response_class=RedirectResponse, name="admin_manage_classroom_add")
async def add_classroom_by_admin(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields from modal
    location: str = Form(...),
    capacity_str: Optional[str] = Form(None) # Capacity as string first
):
    redirect_url = request.url_for('admin_manage_classrooms_list')
    capacity: Optional[int] = None
    try:
        # Convert capacity string to int, allow empty string/None
        if capacity_str and capacity_str.strip():
            capacity = int(capacity_str)

        new_classroom = classroom_service.create_classroom(
            db=db, location=location, capacity=capacity
        )
        logger.info(f"Admin {current_user.username} created classroom {new_classroom.id} ('{new_classroom.location}')")
        success_msg = urllib.parse.quote(f"Classroom '{new_classroom.location}' created successfully.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch duplicate location or bad capacity format
        logger.warning(f"Admin {current_user.username} failed to add classroom: {e}")
        error_msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error adding classroom: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while adding the classroom.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)

# UPDATE (Process Edit Classroom Form)
# Final URL: /admin/classrooms/{classroom_id}/edit
@router.post("/{classroom_id}/edit", response_class=RedirectResponse, name="admin_manage_classroom_edit")
async def edit_classroom_by_admin(
    classroom_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Require admin
    # Form fields from modal
    location: str = Form(...),
    capacity_str: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_classrooms_list')
    capacity: Optional[int] = None
    update_data = {}
    try:
        # Convert capacity and prepare update data
        if capacity_str and capacity_str.strip():
            capacity = int(capacity_str)
        # Include capacity in update_data only if provided (even if empty string -> None)
        if capacity_str is not None:
             update_data['capacity'] = capacity if capacity_str.strip() else None

        update_data['location'] = location

        updated_classroom = classroom_service.update_classroom(
            db=db, classroom_id=classroom_id, update_data=update_data
        )
        if updated_classroom is None:
             raise ValueError("Classroom not found.")

        logger.info(f"Admin {current_user.username} updated classroom {classroom_id}")
        success_msg = urllib.parse.quote(f"Classroom '{updated_classroom.location}' updated successfully.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e: # Catch duplicate location, bad capacity format, not found
        logger.warning(f"Admin {current_user.username} failed to update classroom {classroom_id}: {e}")
        error_msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error updating classroom {classroom_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while updating the classroom.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)

# DELETE Classroom
# Final URL: /admin/classrooms/{classroom_id}/delete
@router.post("/{classroom_id}/delete", response_class=RedirectResponse, name="admin_manage_classroom_delete")
async def delete_classroom_by_admin(
    classroom_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin) # Require admin
):
    redirect_url = request.url_for('admin_manage_classrooms_list')
    classroom_loc_temp = f"ID {classroom_id}"
    try:
        # Optional: Get location before deleting
        classroom = classroom_service.get_classroom_by_id(db, classroom_id)
        if classroom: classroom_loc_temp = classroom.location

        success = classroom_service.delete_classroom(db=db, classroom_id=classroom_id)
        if not success:
             raise ValueError("Classroom not found.") # Should be caught by service check or FK

        logger.info(f"Admin {current_user.username} deleted classroom {classroom_id}")
        success_msg = urllib.parse.quote(f"Classroom '{classroom_loc_temp}' deleted successfully.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch "cannot delete due to dependencies", "not found"
         logger.warning(f"Admin {current_user.username} failed to delete classroom {classroom_id}: {e}")
         error_msg = urllib.parse.quote(str(e))
         return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Admin {current_user.username} encountered unexpected error deleting classroom {classroom_id}: {e}", exc_info=True)
        error_msg = urllib.parse.quote("An unexpected error occurred while deleting the classroom.")
        return RedirectResponse(url=f"{redirect_url}", status_code=status.HTTP_303_SEE_OTHER)