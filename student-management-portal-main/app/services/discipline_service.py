# app/services/discipline_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from app import models
from typing import List, Optional, Dict, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

# === Discipline Record Management ===

def get_all_discipline_records(db: Session, student_id: Optional[int] = None) -> List[models.DisciplineRecord]:
    """Retrieves all discipline records, optionally filtered by student."""
    query = db.query(models.DisciplineRecord).options(
        joinedload(models.DisciplineRecord.student).joinedload(models.Student.user) # Load student -> user
    )
    if student_id:
        query = query.filter(models.DisciplineRecord.student_id == student_id)

    # Order by incident date descending
    query = query.order_by(desc(models.DisciplineRecord.incident_date), models.DisciplineRecord.created_at.desc())
    return query.all()

def get_discipline_record_by_id(db: Session, record_id: int) -> Optional[models.DisciplineRecord]:
    """Retrieves a single discipline record by its ID."""
    return db.query(models.DisciplineRecord).options(
        joinedload(models.DisciplineRecord.student).joinedload(models.Student.user)
    ).filter(models.DisciplineRecord.id == record_id).first()


def create_discipline_record(db: Session, student_id: int, incident_date: date,
                             incident_description: str, action_taken: Optional[str]) -> models.DisciplineRecord:
    """Creates a new discipline record for a student."""
    # 1. Check if student exists
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student: raise ValueError(f"Student with ID {student_id} not found.")

    # 2. Validate required fields
    if not incident_description or not incident_description.strip():
        raise ValueError("Incident description cannot be empty.")
    if not incident_date: # Should have default, but check anyway
        raise ValueError("Incident date is required.")

    # 3. Create record
    db_record = models.DisciplineRecord(
        student_id=student_id,
        incident_date=incident_date,
        incident_description=incident_description.strip(),
        action_taken=action_taken.strip() if action_taken else None
    )
    db.add(db_record)
    try:
        db.commit(); db.refresh(db_record)
        logger.info(f"Created discipline record {db_record.id} for student {student_id}")
        return db_record
    except Exception as e:
        db.rollback(); logger.error(f"Error creating discipline record: {e}");
        raise ValueError("Database error creating discipline record.")


def update_discipline_record(db: Session, record_id: int, update_data: Dict[str, Any]) -> Optional[models.DisciplineRecord]:
    """Updates an existing discipline record."""
    db_record = get_discipline_record_by_id(db, record_id)
    if not db_record: return None

    updated = False
    # Note: student_id should not typically change

    if 'incident_date' in update_data:
        new_date = update_data['incident_date'] # Expected date object
        if not new_date: raise ValueError("Incident date cannot be empty.")
        if db_record.incident_date != new_date: db_record.incident_date = new_date; updated = True

    if 'incident_description' in update_data:
        new_desc = update_data['incident_description']
        if not new_desc or not new_desc.strip(): raise ValueError("Incident description cannot be empty.")
        new_desc_cleaned = new_desc.strip()
        if db_record.incident_description != new_desc_cleaned: db_record.incident_description = new_desc_cleaned; updated = True

    if 'action_taken' in update_data:
        new_action = update_data['action_taken'] # Expected string or None
        new_action_cleaned = new_action.strip() if new_action else None
        if db_record.action_taken != new_action_cleaned: db_record.action_taken = new_action_cleaned; updated = True

    if not updated: return db_record

    try:
        db.add(db_record); db.commit(); db.refresh(db_record)
        logger.info(f"Updated discipline record {record_id}")
        return db_record
    except Exception as e:
        db.rollback(); logger.error(f"Error updating discipline record {record_id}: {e}");
        raise ValueError("Database error updating discipline record.")


def delete_discipline_record(db: Session, record_id: int) -> bool:
    """Deletes a discipline record."""
    db_record = get_discipline_record_by_id(db, record_id)
    if not db_record: return False

    # No typical dependencies to check, but could add business rules

    try:
        db.delete(db_record); db.commit()
        logger.info(f"Deleted discipline record {record_id} for student {db_record.student_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting discipline record {record_id}: {e}");
        raise ValueError("Database error deleting discipline record.")