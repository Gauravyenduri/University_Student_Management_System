# app/services/student_service.py
# (Create this file if it doesn't exist)

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from app import models
from app.services import auth_service # For password hashing
from datetime import date
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_students(db: Session) -> List[models.Student]:
    """Retrieves all student records, potentially with user info joined."""
    # Eager load user and department to avoid N+1 queries in the template
    return db.query(models.Student).options(
        joinedload(models.Student.user),
        joinedload(models.Student.department) # Eager load department
    ).order_by(models.Student.name).all()

def get_student_by_id_with_user(db: Session, student_id: int) -> Optional[models.Student]:
    """Retrieves a single student by ID, ensuring user and department info is loaded."""
    return db.query(models.Student).options(
        joinedload(models.Student.user), # Eager load user
        joinedload(models.Student.department) # Eager load department
    ).filter(models.Student.id == student_id).first()

def create_student_with_user(
    db: Session, name: str, email: str, username: str, raw_password: str,
    dob: Optional[date], phone: Optional[str], address: Optional[str],
    department_id: Optional[int] = None # Add department_id parameter
) -> models.Student:
    """Creates a User and a linked Student record, optionally assigning a department."""
    # Check for existing user first
    existing_user = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()
    if existing_user:
        if existing_user.username == username:
            raise ValueError(f"Username '{username}' already exists.")
        else:
            raise ValueError(f"Email '{email}' already exists.")

    hashed_password = auth_service.get_password_hash(raw_password)

    # Create User first
    db_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=models.UserRole.STUDENT, # Assign STUDENT role
        is_active=True # Activate by default
    )
    db.add(db_user)
    # We need the user ID, flush to get it assigned by the DB
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error during user flush: {e}")
        # Check constraints again or re-raise a clearer error
        if "users_username_key" in str(e):
             raise ValueError(f"Username '{username}' already exists (concurrent request?).")
        elif "users_email_key" in str(e):
             raise ValueError(f"Email '{email}' already exists (concurrent request?).")
        else:
             raise ValueError("Database error creating user.")


    # Create Student, linking user_id
    db_student = models.Student(
        name=name,
        dob=dob,
        phone=phone,
        address=address,
        user_id=db_user.id, # Link to the newly created user
        department_id=department_id # Assign department
    )
    db.add(db_student)

    try:
        db.commit()
        db.refresh(db_student) # Load relationships like db_student.user
        db.refresh(db_user) # Refresh user too
        return db_student
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing student/user creation: {e}", exc_info=True)
        raise ValueError("Failed to create student record due to database error.")


def update_student_and_user(db: Session, student_id: int, update_data: Dict[str, Any]) -> models.Student:
    """Updates student and potentially linked user details."""
    db_student = get_student_by_id_with_user(db, student_id)
    if not db_student:
        raise ValueError("Student not found") # Or return None/False

    db_user = db_student.user
    if not db_user:
         # This shouldn't happen if data integrity is maintained
         raise ValueError("Associated user account not found for this student.")

    # Update Student fields
    db_student.name = update_data.get('name', db_student.name)
    db_student.dob = update_data.get('dob', db_student.dob)
    db_student.phone = update_data.get('phone', db_student.phone)
    db_student.address = update_data.get('address', db_student.address)
    db_student.department_id = update_data.get('department_id')

    # Update User fields (handle potential email conflicts)
    new_email = update_data.get('user_email')
    if new_email and new_email != db_user.email:
        # Check if the new email is already taken by another user
        existing_user = db.query(models.User).filter(models.User.email == new_email, models.User.id != db_user.id).first()
        if existing_user:
            raise ValueError(f"Email '{new_email}' is already in use by another account.")
        db_user.email = new_email

    # Note: Handle username changes carefully if ever implemented.

    try:
        db.add(db_student) # Add both objects to session in case user was modified
        db.add(db_user)
        db.commit()
        db.refresh(db_student)
        db.refresh(db_user)
        return db_student
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating student {student_id}: {e}")
        if "users_email_key" in str(e):
            raise ValueError(f"Email '{new_email}' is already in use (concurrent request?).")
        else:
            raise ValueError("Database error updating student/user.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing student/user update {student_id}: {e}", exc_info=True)
        raise ValueError("Failed to update student record due to database error.")

def delete_student_and_user(db: Session, student_id: int) -> bool:
    """Deletes a student and the associated user record."""
    # Assumes cascade delete is set correctly on User.student_profile relationship
    # If not, you need to delete the user manually first or after.
    # For safety, let's query both first.
    db_student = db.query(models.Student).options(joinedload(models.Student.user)).filter(models.Student.id == student_id).first()
    if not db_student:
        return False # Indicate student not found

    db_user_to_delete = db_student.user

    try:
        # If cascade is configured correctly on User.student_profile,
        # deleting the student might be enough if the relationship is defined there.
        # However, let's explicitly delete the Student. If cascade works, user goes too.
        # If cascade is on Student.user, deleting User might be the trigger.
        # Safest might be explicitly deleting both if cascade isn't guaranteed/tested.

        # Option 1: Assuming cascade delete configured on User.student_profile = relationship(..., cascade="all, delete-orphan")
        # db.delete(db_student)

        # Option 2: Explicitly delete both (Student first if User has FK)
        # This is generally safer if unsure about cascades or if FK constraints prevent user delete first
        db.delete(db_student)
        if db_user_to_delete:
             db.delete(db_user_to_delete) # Delete associated user
        else:
             logger.warning(f"Student {student_id} did not have an associated user to delete.")


        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting student {student_id} or associated user: {e}", exc_info=True)
        return False

def update_student_profile(db: Session, student_id: int, update_data: Dict[str, Any]) -> Optional[models.Student]:
    """Updates basic profile details for a student."""
    db_student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not db_student:
        return None

    updated = False
    if 'name' in update_data and update_data['name'] and db_student.name != update_data['name'].strip():
        db_student.name = update_data['name'].strip()
        updated = True
    if 'dob' in update_data and db_student.dob != update_data['dob']: # dob is date or None
        db_student.dob = update_data['dob']
        updated = True
    if not updated:
        return db_student # No changes

    try:
        db.add(db_student)
        db.commit()
        db.refresh(db_student)
        logger.info(f"Student profile {student_id} updated.")
        return db_student
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating student profile {student_id}: {e}", exc_info=True)
        raise ValueError("Database error updating profile.")