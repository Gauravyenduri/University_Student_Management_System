# app/services/alumni_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# === Alumni Record Management (Admin) ===

def get_all_alumni(db: Session) -> List[models.Alumni]:
    """Retrieves all alumni records, loading student info."""
    return db.query(models.Alumni).options(
        joinedload(models.Alumni.student).joinedload(models.Student.user) # Load student -> user
    ).order_by(desc(models.Alumni.graduation_year), models.Alumni.id).all() # Example order

def get_alumni_by_id(db: Session, alumni_id: int) -> Optional[models.Alumni]:
    """Retrieves a single alumni record by its primary ID."""
    return db.query(models.Alumni).options(
        joinedload(models.Alumni.student).joinedload(models.Student.user)
    ).filter(models.Alumni.id == alumni_id).first()

def get_alumni_by_student_id(db: Session, student_id: int) -> Optional[models.Alumni]:
    """Retrieves the alumni record associated with a specific student ID."""
    return db.query(models.Alumni).options(
        joinedload(models.Alumni.student).joinedload(models.Student.user)
    ).filter(models.Alumni.student_id == student_id).first()


def create_alumni_record(db: Session, student_id: int, graduation_year: Optional[int],
                         current_job: Optional[str], current_employer: Optional[str],
                         contact_info: Optional[str]) -> models.Alumni:
    """Creates a new alumni record, linking it to an existing student."""
    # 1. Check if student exists
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student with ID {student_id} not found.")

    # 2. Check if an alumni record already exists for this student
    existing_alumni = get_alumni_by_student_id(db, student_id)
    if existing_alumni:
        raise ValueError(f"An alumni record already exists for student '{student.name}' (Alumni ID: {existing_alumni.id}).")

    # 3. Create the record
    db_alumni = models.Alumni(
        student_id=student_id,
        graduation_year=graduation_year,
        current_job=current_job,
        current_employer=current_employer,
        contact_info=contact_info
    )
    db.add(db_alumni)
    try:
        db.commit(); db.refresh(db_alumni)
        logger.info(f"Created alumni record {db_alumni.id} for student {student_id}")
        return db_alumni
    except IntegrityError as e: # Catch potential unique constraint on student_id
        db.rollback()
        logger.error(f"DB integrity error creating alumni record: {e}")
        raise ValueError(f"Database error: Could not create alumni record, possibly duplicate student link.")
    except Exception as e:
        db.rollback(); logger.error(f"Error committing alumni creation: {e}");
        raise ValueError("Database error creating alumni record.")


def update_alumni_record(db: Session, alumni_id: int, update_data: Dict[str, Any]) -> Optional[models.Alumni]:
    """Updates an existing alumni record."""
    db_alumni = get_alumni_by_id(db, alumni_id)
    if not db_alumni: return None

    updated = False
    # student_id should NOT be changed

    if 'graduation_year' in update_data:
        new_year = update_data['graduation_year'] # Expected int or None
        if db_alumni.graduation_year != new_year: db_alumni.graduation_year = new_year; updated = True
    if 'current_job' in update_data:
        new_job = update_data['current_job']
        if db_alumni.current_job != new_job: db_alumni.current_job = new_job; updated = True
    if 'current_employer' in update_data:
        new_employer = update_data['current_employer']
        if db_alumni.current_employer != new_employer: db_alumni.current_employer = new_employer; updated = True
    if 'contact_info' in update_data:
        new_contact = update_data['contact_info']
        if db_alumni.contact_info != new_contact: db_alumni.contact_info = new_contact; updated = True

    if not updated: return db_alumni

    try:
        db.add(db_alumni); db.commit(); db.refresh(db_alumni)
        logger.info(f"Updated alumni record {alumni_id}")
        return db_alumni
    except Exception as e:
        db.rollback(); logger.error(f"Error updating alumni record {alumni_id}: {e}");
        raise ValueError("Database error updating alumni record.")


def delete_alumni_record(db: Session, alumni_id: int) -> bool:
    """Deletes an alumni record."""
    db_alumni = get_alumni_by_id(db, alumni_id)
    if not db_alumni: return False

    # No typical dependencies to check unless other models link to Alumni.id

    try:
        db.delete(db_alumni); db.commit()
        logger.info(f"Deleted alumni record {alumni_id} (associated with student {db_alumni.student_id})")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting alumni record {alumni_id}: {e}");
        raise ValueError("Database error deleting alumni record.")