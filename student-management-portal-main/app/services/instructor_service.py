# app/services/instructor_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func # Import func for lower case comparison
from app import models
from app.services import auth_service # For password hashing
from datetime import date
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_instructors(db: Session) -> List[models.Instructor]:
    """Retrieves all instructor records, loading user and department info."""
    return db.query(models.Instructor).options(
        joinedload(models.Instructor.user),       # Eager load user
        joinedload(models.Instructor.department)  # Eager load department
    ).order_by(models.Instructor.name).all()

def get_instructor_by_id_with_user(db: Session, instructor_id: int) -> Optional[models.Instructor]:
    """Retrieves a single instructor by ID, ensuring user and department info is loaded."""
    return db.query(models.Instructor).options(
        joinedload(models.Instructor.user),
        joinedload(models.Instructor.department)
    ).filter(models.Instructor.id == instructor_id).first()

def create_instructor_with_user(
    db: Session, name: str, email: str, username: str, raw_password: str,
    qualification: Optional[str], department_id: Optional[int], phone: Optional[str]
) -> models.Instructor:
    """Creates a User and a linked Instructor record."""
    # Ensure case-insensitive checks for username and email
    existing_user = db.query(models.User).filter(
        (func.lower(models.User.username) == func.lower(username)) |
        (func.lower(models.User.email) == func.lower(email) )
    ).first()
    if existing_user:
        if existing_user.username == username:
            raise ValueError(f"Username '{username}' already exists.")
        elif existing_user.email == email:
            raise ValueError(f"Email '{email}' already exists.")

    # Check if department exists
    if department_id and not db.query(models.Department).filter(models.Department.id == department_id).first():
         raise ValueError(f"Department with ID {department_id} not found.")


    hashed_password = auth_service.get_password_hash(raw_password)

    db_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=models.UserRole.INSTRUCTOR, # Assign INSTRUCTOR role
        is_active=True
    )
    db.add(db_user)
    try:
        db.flush() # Get user ID
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error during user flush for instructor: {e}")
        # Refine error message based on constraint if possible
        raise ValueError("Database error creating user account. Username or email might already exist.")

    db_instructor = models.Instructor(
        name=name,
        qualification=qualification,
        department_id=department_id,
        phone=phone,
        user_id=db_user.id # Link user
    )
    db.add(db_instructor)

    try:
        db.commit()
        db.refresh(db_instructor)
        db.refresh(db_user)
        return db_instructor
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing instructor/user creation: {e}", exc_info=True)
        raise ValueError("Failed to create instructor record due to database error.")


def update_instructor_and_user(db: Session, instructor_id: int, update_data: Dict[str, Any]) -> models.Instructor:
    """Updates instructor and potentially linked user details."""
    db_instructor = get_instructor_by_id_with_user(db, instructor_id)
    if not db_instructor:
        raise ValueError("Instructor not found")

    db_user = db_instructor.user
    if not db_user:
         raise ValueError("Associated user account not found for this instructor.")

    # Update Instructor fields
    db_instructor.name = update_data.get('name', db_instructor.name)
    db_instructor.qualification = update_data.get('qualification', db_instructor.qualification)
    db_instructor.phone = update_data.get('phone', db_instructor.phone)

    new_dept_id = update_data.get('department_id')
    if new_dept_id is not None: # Allow setting department to None or changing it
         # Check if new department ID is valid (if not None)
         if new_dept_id and not db.query(models.Department).filter(models.Department.id == new_dept_id).first():
              raise ValueError(f"Department with ID {new_dept_id} not found.")
         db_instructor.department_id = new_dept_id


    # Update User fields (handle potential email conflicts)
    new_email = update_data.get('user_email')
    if new_email and func.lower(new_email) != func.lower(db_user.email):
        existing_user = db.query(models.User).filter(
            func.lower(models.User.email) == func.lower(new_email),
            models.User.id != db_user.id
        ).first()
        if existing_user:
            raise ValueError(f"Email '{new_email}' is already in use by another account.")
        db_user.email = new_email

    try:
        db.add(db_instructor)
        db.add(db_user)
        db.commit()
        db.refresh(db_instructor)
        db.refresh(db_user)
        # Ensure relationships are refreshed if needed
        db.refresh(db_instructor.department) if db_instructor.department_id else None
        return db_instructor
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating instructor {instructor_id}: {e}")
        raise ValueError("Database error updating instructor/user. Email might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing instructor/user update {instructor_id}: {e}", exc_info=True)
        raise ValueError("Failed to update instructor record due to database error.")

def delete_instructor_and_user(db: Session, instructor_id: int) -> bool:
    """Deletes an instructor and the associated user record."""
    db_instructor = db.query(models.Instructor).options(
        db.joinedload(models.Instructor.user),
        db.joinedload(models.Instructor.headed_department) # Load if they head a department
    ).filter(models.Instructor.id == instructor_id).first()

    if not db_instructor:
        return False

    # === Check if Instructor is a Head of Department ===
    if db_instructor.headed_department:
        dept_name = db_instructor.headed_department.name
        logger.warning(f"Attempted to delete Instructor {instructor_id} ('{db_instructor.name}') who is Head of Department for '{dept_name}'.")
        # Option 1: Prevent deletion (Safer)
        raise ValueError(f"Cannot delete instructor '{db_instructor.name}' because they are the Head of Department for '{dept_name}'. Assign a new HoD first.")
        # Option 2: Set HoD to NULL on the department (Use with caution)
        # logger.info(f"Setting Head of Department to NULL for '{dept_name}' before deleting instructor {instructor_id}.")
        # db_instructor.headed_department.head_of_department_id = None
        # db.add(db_instructor.headed_department)
        # try:
        #     db.flush() # Apply the change immediately before deleting instructor
        # except Exception as e:
        #     db.rollback()
        #     logger.error(f"Failed to nullify HoD for department '{dept_name}' before deleting instructor {instructor_id}: {e}")
        #     raise ValueError(f"Could not remove instructor as HoD for '{dept_name}'. Deletion aborted.")
    # === End Check ===


    db_user_to_delete = db_instructor.user

    try:
        db.delete(db_instructor)
        if db_user_to_delete:
             db.delete(db_user_to_delete)
        else:
             logger.warning(f"Instructor {instructor_id} did not have an associated user to delete.")

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting instructor {instructor_id} or associated user: {e}", exc_info=True)
        return False