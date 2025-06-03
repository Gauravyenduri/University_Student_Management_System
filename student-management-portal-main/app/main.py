from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import os
from dotenv import load_dotenv
from typing import Optional, List
from fastapi.responses import HTMLResponse
import logging
from app.database import SessionLocal
# Local imports
from app.database import get_db, engine
from app.models import Base
from app import models
from app.models import Base, User, UserRole # Import User and UserRole
from app.services import auth_service
# Import all route modules
from app.routes import (
    auth, admin, showcase,
    student,
     instructor,
    course, 
    student_dashboard,
    instructor_dashboard,
     schedule, 
    fee, scholarship, 
    hostel, 
    discipline, 
    club, 
    complaint, 
    alumni, 
    library, 
    department,
     classroom,
     home,
     showcase
)

# Load environment variables
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Student Management System",
    description="A comprehensive system for managing educational institutions",
    version="1.0.0"
)

# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Checks for and creates the default admin user on startup."""
    logger.info("Running startup event...")
    db: Session = SessionLocal() # Create a new session explicitly for startup
    try:
        admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", 'admin')
        admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", 'admin@example.com')
        admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", 'admin123')

        if not all([admin_username, admin_email, admin_password]):
            logger.warning("Default admin credentials not found in .env. Skipping default admin creation.")
            return

        # Check if admin user already exists
        existing_admin = db.query(User).filter(
            (User.username == admin_username) | (User.email == admin_email)
        ).first()

        if existing_admin:
            logger.info(f"Default admin user '{admin_username}' already exists.")
        else:
            logger.info(f"Creating default admin user '{admin_username}'...")
            hashed_password = auth_service.get_password_hash(admin_password)
            default_admin = User(
                username=admin_username,
                email=admin_email,
                hashed_password=hashed_password,
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(default_admin)
            db.commit()
            logger.info(f"Default admin user '{admin_username}' created successfully.")
            logger.warning(f"IMPORTANT: Log in as '{admin_username}' with the default password and change it immediately!")

    except Exception as e:
        logger.error(f"Error during startup event (admin creation): {e}")
        # Depending on the error, you might want to db.rollback() here,
        # but often commit errors are handled by SQLAlchemy raising exceptions earlier.
    finally:
        db.close() # Ensure the session is closed
    logger.info("Startup event finished.")



# Configure templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all route modules
app.include_router(home.router, tags=["Home"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(student.router, prefix="/admin/students", tags=["Admin - Student Management"])
app.include_router(instructor.router, prefix="/admin/instructors", tags=["Instructors"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(
    course.router, prefix="/admin/courses", tags=["Admin - Course Management"]
)
app.include_router(
    classroom.router, prefix="/admin/classrooms", tags=["Admin - Classroom Management"]
)
app.include_router(
    schedule.router, prefix="/admin/schedules", tags=["Admin - Schedule Management"]
)
app.include_router(
    fee.router, prefix="/admin/fees", tags=["Admin - Fee Management"]
)
app.include_router(
    scholarship.router, prefix="/admin/scholarships", tags=["Admin - Scholarship Management"]
)
app.include_router(
    student_dashboard.router,
     prefix="/student", # Prefix defined IN student.py now
     tags=["Student Portal"]
)
app.include_router(
    instructor_dashboard.router, # Router defined in instructor_dashboard.py
    prefix="/instructor", # Set prefix for instructor routes
    tags=["Instructor Portal"]
)
app.include_router(
    library.router, prefix="/admin/library", tags=["Admin - Library Management"]
)
app.include_router(
    hostel.router,
    prefix="/admin/hostels", # Mount under admin section
    tags=["Admin - Hostel Management"] 
)
app.include_router(
    discipline.router,
    prefix="/instructor/discipline",
    tags=["Instructor - Discipline"] 
)
app.include_router(
    club.router,
    prefix="/admin/clubs", # Mount under admin section
    tags=["Admin - Club Management"] # Tag for docs
)
app.include_router(
    complaint.router,
    prefix="/admin/complaints", # Mount under admin section
    tags=["Admin - Complaint Management"] # Tag for docs
)
app.include_router(
    alumni.router,
    prefix="/admin/alumni", # Mount under admin section
    tags=["Admin - Alumni Management"] # Tag for docs
)
app.include_router(showcase.router, prefix="/showcase", tags=["Showcase"]) # Mount here

app.include_router(
    department.router,
    prefix="/admin/departments",
    tags=["Admin - Department Management"]
)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)