# app/routes/club.py

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
from app.services import auth_service, club_service # Import club service
from app.models import UserRole # Import models needed

logger = logging.getLogger(__name__)

# THIS ROUTER IS MOUNTED UNDER /admin/clubs IN main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# === Admin Management of Clubs ===

# READ (List Clubs)
@router.get("/", response_class=HTMLResponse, name="admin_manage_clubs")
async def list_clubs_for_admin(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin), # Admin Auth
    toast_error: Optional[str] = Query(None),
    toast_success: Optional[str] = Query(None)
):
    """Displays list of all clubs for admin view."""
    logger.info(f"Admin {current_user.username} accessing clubs list.")
    try:
        clubs = club_service.get_all_clubs(db)
    except Exception as e:
        logger.error(f"Failed to fetch clubs: {e}", exc_info=True)
        clubs = []
        toast_error = toast_error or "Failed to load club list."

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; # etc.
    context = {
        "request": request, "user": current_user, "UserRole": UserRole,
        "clubs": clubs,
        "page_title": "Manage Clubs & Activities",
        "toast_error": toast_error, "toast_success": toast_success
    }
    # New template path needed
    return templates.TemplateResponse("admin/manage_clubs.html", context)


# CREATE Club (Process Add Form)
@router.post("/add", response_class=RedirectResponse, name="admin_add_club")
async def add_club_by_admin(
    request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
    # Form fields from modal
    name: str = Form(...),
    club_type: Optional[str] = Form(None, alias="type"), # Match HTML name 'type'
    description: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_clubs')
    logger.info(f"Admin {current_user.username} attempting to add club.")
    try:
        new_club = club_service.create_club(
            db, name=name, club_type=club_type, description=description
        )
        toast_msg = urllib.parse.quote(f"Club '{new_club.name}' created successfully.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error adding club: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error adding club: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected server error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# UPDATE Club (Process Edit Form)
@router.post("/{club_id}/edit", response_class=RedirectResponse, name="admin_edit_club")
async def edit_club_by_admin(
    club_id: int, request: Request, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin),
     # Form fields from modal
    name: str = Form(...),
    club_type: Optional[str] = Form(None, alias="type"),
    description: Optional[str] = Form(None)
):
    redirect_url = request.url_for('admin_manage_clubs')
    update_data = {
        "name": name,
        "type": club_type,
        "description": description
    }
    try:
        updated_club = club_service.update_club(db, club_id, update_data)
        if updated_club is None: raise ValueError("Club not found.")

        toast_msg = urllib.parse.quote(f"Club '{updated_club.name}' updated.")
        return RedirectResponse(f"{redirect_url}?toast_success={toast_msg}", status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        toast_msg = urllib.parse.quote(f"Error updating club: {e}")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Unexpected error updating club {club_id}: {e}", exc_info=True)
        toast_msg = urllib.parse.quote("An unexpected error occurred.")
        return RedirectResponse(f"{redirect_url}?toast_error={toast_msg}", status.HTTP_303_SEE_OTHER)


# DELETE Club
@router.post("/{club_id}/delete", response_class=JSONResponse, name="admin_delete_club")
async def delete_club_by_admin(
    club_id: int, db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    """Handles deletion of a club definition by an admin via fetch."""
    logger.info(f"Admin {current_user.username} attempting delete club {club_id}.")
    try:
        success = club_service.delete_club(db, club_id)
        if not success: raise ValueError("Club not found.")
        return JSONResponse(content={"success": True, "message": "Club deleted successfully."})
    except ValueError as e: # Catch service errors (not found, dependencies)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "message": str(e)})
    except Exception as e:
        logger.error(f"Error deleting club {club_id}: {e}", exc_info=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"success": False, "message": "Unexpected error."})