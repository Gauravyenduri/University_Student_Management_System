# app/routes/showcase.py (New File)

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

# Local imports
from app import database, models
from app.services import auth_service, alumni_service # Need alumni service
from app.models import UserRole

logger = logging.getLogger(__name__)

# This router can be mounted at a common path like /showcase
router = APIRouter(
    tags=["Showcase"]
)
templates = Jinja2Templates(directory="app/templates")

# === Alumni Showcase Page ===
@router.get("/alumni", response_class=HTMLResponse, name="showcase_alumni")
async def show_alumni_page(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    # Require user to be logged in, but doesn't matter which role
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Displays the public-facing (within portal) Alumni Showcase page."""
    logger.info(f"User {current_user.username} accessing alumni showcase.")
    error_message = None
    alumni_list = []
    try:
        # Fetch all alumni records (service loads student details)
        alumni_list = alumni_service.get_all_alumni(db)
        # Optional: Further filtering? E.g., only show alumni with job info?
        # alumni_list = [a for a in alumni_list if a.current_job or a.current_employer]
    except Exception as e:
        logger.error(f"Failed to fetch alumni for showcase: {e}", exc_info=True)
        error_message = "Could not load alumni information."

    # Set cache headers? Maybe allow some caching here? Optional.
    # response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate";

    context = {
        "request": request,
        "user": current_user, # For layout
        "UserRole": UserRole, # For layout
        "alumni_list": alumni_list,
        "page_title": "Alumni Showcase",
        "error_message": error_message
    }
    # New template path
    return templates.TemplateResponse("showcase/alumni_showcase.html", context)