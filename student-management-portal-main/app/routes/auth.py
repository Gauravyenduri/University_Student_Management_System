# app/routes/auth.py

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from email_validator import validate_email, EmailNotValidError # For email validation
from fastapi.security import OAuth2PasswordRequestForm

# Local imports
from app import database, models
from app.services import auth_service # Import the auth service module
from app.models import UserRole

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# --- Login Routes ---

@router.get("/login", response_class=HTMLResponse, name="login_form")
async def login_form(request: Request):
    """Displays the login form."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", name="login")
async def login_for_access_token(
    response: Response, # Inject Response to set cookie
    request: Request,
    db: Session = Depends(database.get_db),
    # Use Form data instead of OAuth2PasswordRequestForm for more flexibility
    username: str = Form(...),
    password: str = Form(...)
):
    """Handles user login, sets JWT cookie, and redirects."""
    user = auth_service.authenticate_user(db, username=username, password=password)
    if not user:
        # Re-render login form with an error message
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # Create access token
    access_token_expires = timedelta(minutes=auth_service.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # Determine redirect URL based on role
    if user.role == UserRole.ADMIN:
        redirect_url = request.url_for('admin_dashboard') # Assumes you name admin dashboard route
    elif user.role == UserRole.INSTRUCTOR:
        redirect_url = request.url_for('instructor_dashboard') # Assumes you name instructor dashboard route
    elif user.role == UserRole.STUDENT:
        redirect_url = request.url_for('student_dashboard') # Assumes you name student dashboard route
    else:
        redirect_url = "/" # Fallback, should ideally not happen

    # Create redirect response and SET THE COOKIE
    redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    redirect_response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # ! Important: Protects against XSS
        max_age=int(access_token_expires.total_seconds()), # Cookie expiry in seconds
        expires=int(access_token_expires.total_seconds()), # For older browsers
        samesite="lax", # Recommended for security (lax or strict)
        # secure=True, # ! Uncomment this in PRODUCTION if served over HTTPS
    )
    return redirect_response

# --- Logout Route ---

@router.post("/logout", name="logout") # Use POST for actions that change state
async def logout(response: Response, request: Request):
    """Logs the user out by deleting the cookie."""
    # Redirect to login page after logout
    redirect_response = RedirectResponse(url=request.url_for('login_form'), status_code=status.HTTP_303_SEE_OTHER)
    # Delete the cookie
    redirect_response.delete_cookie(key="access_token", httponly=True, samesite="lax") # Match settings used in set_cookie
    return redirect_response

# --- Change Password Routes ---

@router.get("/change-password", response_class=HTMLResponse, name="change_password_form")
async def change_password_form(
    request: Request,
    current_user: models.User = Depends(auth_service.get_current_user) # Requires login
):
    """Displays the change password form."""
    return templates.TemplateResponse("change_password.html", {"request": request, "user": current_user})

@router.post("/change-password", name="change_password")
async def change_password(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user), # Requires login
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Handles changing the user's password."""
    context = {"request": request, "user": current_user} # Context for re-rendering form on error

    # 1. Verify current password
    if not auth_service.verify_password(current_password, current_user.hashed_password):
        context["error"] = "Incorrect current password."
        return templates.TemplateResponse("change_password.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    # 2. Verify new password confirmation
    if new_password != confirm_password:
        context["error"] = "New passwords do not match."
        return templates.TemplateResponse("change_password.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    # 3. Optional: Add complexity checks for the new password here (length, characters, etc.)
    if len(new_password) < 8: # Example minimum length
         context["error"] = "New password must be at least 8 characters long."
         return templates.TemplateResponse("change_password.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    # 4. Hash and update the password
    current_user.hashed_password = auth_service.get_password_hash(new_password)
    db.add(current_user)
    db.commit()

    # Determine the appropriate dashboard based on user role
    if current_user.role == "ADMIN":
        redirect_url = request.url_for('admin_dashboard')
    elif current_user.role == "INSTRUCTOR":
        redirect_url = request.url_for('instructor_dashboard')
    elif current_user.role == "STUDENT":
        redirect_url = request.url_for('student_dashboard')
    else:
        redirect_url = request.url_for('read_home')

    # Redirect to the appropriate dashboard
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# --- Token endpoint (used internally by OAuth2PasswordBearer if using forms directly with it) ---
# We handle login manually above to set cookies, but keep this for potential future use or if OAuth2PasswordBearer expects it.
@router.post("/token", include_in_schema=False) # Often excluded from OpenAPI docs
async def login_for_token_internal(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db)
):
    """Provides a token endpoint (primarily for header-based auth flows)."""
    user = auth_service.authenticate_user(db, username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth_service.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}