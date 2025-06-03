# app/services/guardian_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_guardians_for_student(db: Session, student_id: int) -> List[models.Guardian]:
    """Retrieves all guardians linked to a specific student."""
    return db.query(models.Guardian).filter(models.Guardian.student_id == student_id)\
           .order_by(models.Guardian.id).all() # Or order by name

def get_guardian_by_id(db: Session, guardian_id: int, student_id: int) -> Optional[models.Guardian]:
    """Retrieves a specific guardian ensuring it belongs to the student."""
    return db.query(models.Guardian).filter(
        models.Guardian.id == guardian_id,
        models.Guardian.student_id == student_id # Ownership check
    ).first()

def add_guardian_for_student(db: Session, student_id: int, name: str,
                             relationship_type: Optional[str], phone: Optional[str],
                             email: Optional[str], address: Optional[str]) -> models.Guardian:
    """Adds a new guardian record linked to a student."""
    # Check student exists
    if not db.query(models.Student.id).filter(models.Student.id == student_id).first():
         raise ValueError("Student not found.")
    if not name or not name.strip(): raise ValueError("Guardian name is required.")

    db_guardian = models.Guardian(
        student_id=student_id,
        name=name.strip(),
        relationship_type=relationship_type,
        phone=phone,
        email=email, # Add email validation if needed
        address=address
    )
    db.add(db_guardian)
    try:
        db.commit(); db.refresh(db_guardian)
        logger.info(f"Added guardian {db_guardian.id} for student {student_id}")
        return db_guardian
    except Exception as e:
        db.rollback(); logger.error(f"Error adding guardian for student {student_id}: {e}")
        raise ValueError("Database error adding guardian.")

def update_guardian(db: Session, guardian_id: int, student_id: int, update_data: Dict[str, Any]) -> Optional[models.Guardian]:
    """Updates an existing guardian record, ensuring it belongs to the student."""
    db_guardian = get_guardian_by_id(db, guardian_id, student_id) # Use function with ownership check
    if not db_guardian: return None

    updated = False
    if 'name' in update_data:
         new_name = update_data['name'].strip()
         if not new_name: raise ValueError("Guardian name cannot be empty.")
         if db_guardian.name != new_name: db_guardian.name = new_name; updated = True
    if 'relationship_type' in update_data:
         new_rel = update_data['relationship_type']
         if db_guardian.relationship_type != new_rel: db_guardian.relationship_type = new_rel; updated = True
    if 'phone' in update_data:
         new_phone = update_data['phone']
         if db_guardian.phone != new_phone: db_guardian.phone = new_phone; updated = True
    if 'email' in update_data: # Add validation if needed
         new_email = update_data['email']
         if db_guardian.email != new_email: db_guardian.email = new_email; updated = True
    if 'address' in update_data:
         new_address = update_data['address']
         if db_guardian.address != new_address: db_guardian.address = new_address; updated = True

    if not updated: return db_guardian

    try:
        db.add(db_guardian); db.commit(); db.refresh(db_guardian)
        logger.info(f"Updated guardian {guardian_id} for student {student_id}")
        return db_guardian
    except Exception as e:
        db.rollback(); logger.error(f"Error updating guardian {guardian_id}: {e}")
        raise ValueError("Database error updating guardian.")

def delete_guardian(db: Session, guardian_id: int, student_id: int) -> bool:
    """Deletes a guardian record, ensuring it belongs to the student."""
    db_guardian = get_guardian_by_id(db, guardian_id, student_id) # Use function with ownership check
    if not db_guardian: return False

    try:
        db.delete(db_guardian); db.commit()
        logger.info(f"Deleted guardian {guardian_id} for student {student_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting guardian {guardian_id}: {e}");
        raise ValueError("Database error deleting guardian.")