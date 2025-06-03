# app/routes/home.py (Recommended)

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
# Local imports
from app import models # Import models to access UserRole enum
from app.services.auth_service import get_optional_current_user # Correct import
from app.models import UserRole # Explicit import for clarity

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse, name="read_home") # Give the route a name
async def read_home(
    request: Request,
    current_user: Optional[models.User] = Depends(get_optional_current_user)
):
    """
    Serves the home page if user not logged in, otherwise redirects to dashboard.
    """
    if current_user:
        # User is logged in, redirect based on role
        try:
            if current_user.role == UserRole.ADMIN:
                # Use the 'name' defined in the admin route for the dashboard
                redirect_url = request.url_for('admin_dashboard')
            elif current_user.role == UserRole.INSTRUCTOR:
                # Use the 'name' defined in the instructor route for the dashboard
                 redirect_url = request.url_for('instructor_dashboard')
            elif current_user.role == UserRole.STUDENT:
                 # Use the 'name' defined in the student route for the dashboard
                 redirect_url = request.url_for('student_dashboard')
            else:
                 # Fallback if role is somehow invalid or no dashboard route named
                 redirect_url = "/" # Or maybe a generic '/app' page
        except Exception as e:
             # Handle cases where url_for fails (route name not found)
             print(f"Warning: Could not find named route for dashboard redirect. Error: {e}")
             redirect_url = "/" # Fallback gracefully

        return RedirectResponse(url=redirect_url, status_code=303)

    # User is not logged in, show the home page.
    # Pass UserRole enum to template if needed anywhere (e.g., layout header)
    return templates.TemplateResponse("home.html", {"request": request, "UserRole": UserRole})

# --- IMPORTANT: Define Named Dashboard Routes ---
# You MUST have routes in student.py, instructor.py, admin.py that
# are named 'student_dashboard', 'instructor_dashboard', 'admin_dashboard'
# for the redirects above to work. Example:

# In app/routes/student.py:
# @router.get("/dashboard", response_class=HTMLResponse, name="student_dashboard")
# async def get_student_dashboard(request: Request, current_user: models.User = Depends(auth_service.get_current_active_student)):
#     # Ensure get_current_active_student dependency exists in auth_service
#     return templates.TemplateResponse("student_dashboard.html", {"request": request, "user": current_user})

# Similarly in instructor.py (name="instructor_dashboard") and admin.py (name="admin_dashboard")
# Make sure these dashboard templates exist in app/templates/