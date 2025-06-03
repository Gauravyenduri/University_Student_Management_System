# Example: app/routes/admin.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import models # Import your models
from app.services import auth_service
from app.models import UserRole # Import the enum

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Make sure this route uses the name 'admin_dashboard'
@router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
async def get_admin_dashboard(
    request: Request,
    current_user: models.User = Depends(auth_service.get_current_active_admin)
):
    # --- CRITICAL: Pass necessary context ---
    context = {
        "request": request,
        "user": current_user,
        "UserRole": UserRole, # Pass enum for layout
        "page_title": "Admin Dashboard"
    }

    # ---

    # Add any other dashboard-specific data to the context here
    # context["student_count"] = db.query(models.Student).count() # Example

    return templates.TemplateResponse("admin/admin_dashboard.html", context)

# Do the same for instructor_dashboard, student_dashboard, change_password_form,
# and ANY OTHER page that should have the dashboard layout.