# app/services/hostel_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
# Removed 'date' import as check-in/out are gone
import logging

logger = logging.getLogger(__name__)

# Fixed list of hostel names - Still useful for validation
HOSTEL_NAMES = ["North Hostel", "South Hostel", "Block A", "Block B", "New Wing", "Annex"] # Example List

# === Hostel Assignment Management ===

def get_all_hostel_assignments(db: Session) -> List[models.Hostel]:
    """Retrieves all hostel assignment records, loading student info."""
    return db.query(models.Hostel).options(
        joinedload(models.Hostel.student).joinedload(models.Student.user) # Load student -> user
    ).order_by(models.Hostel.hostel_name, models.Hostel.room_number).all() # Example order

def get_hostel_assignment_by_id(db: Session, assignment_id: int) -> Optional[models.Hostel]:
    """Retrieves a single hostel assignment record by its ID."""
    return db.query(models.Hostel).options(
        joinedload(models.Hostel.student).joinedload(models.Student.user)
    ).filter(models.Hostel.id == assignment_id).first()

def get_hostel_assignment_by_student_id(db: Session, student_id: int) -> Optional[models.Hostel]:
    """Retrieves the hostel assignment for a specific student."""
    # If student_id is unique in Hostel table, this works.
    # If a student could potentially have multiple historical records (which the model doesn't suggest now),
    # you might need more complex logic (e.g., get the latest).
    return db.query(models.Hostel).filter(models.Hostel.student_id == student_id).first()


def assign_hostel(db: Session, student_id: int, hostel_name: str, room_number: Optional[str], # Room can be optional now
                  fees: Optional[float]) -> models.Hostel:
    """Assigns a student to a hostel room."""
    # 1. Check if student exists
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student: raise ValueError(f"Student with ID {student_id} not found.")

    # 2. Check if student already has an assignment (if unique constraint exists)
    existing_assignment = get_hostel_assignment_by_student_id(db, student_id)
    if existing_assignment:
        raise ValueError(f"Student '{student.name}' is already assigned to Hostel '{existing_assignment.hostel_name}'. Edit the existing record.")

    # 3. Validate hostel name
    if hostel_name not in HOSTEL_NAMES:
         raise ValueError(f"Invalid hostel name '{hostel_name}'.")

    # 4. Validate room number if provided
    room_number_cleaned = room_number.strip() if room_number else None
    # if not room_number_cleaned: raise ValueError("Room number is required.") # Removed required constraint based on model

    # 5. Create record
    db_assignment = models.Hostel(
        student_id=student_id,
        hostel_name=hostel_name,
        room_number=room_number_cleaned, # Store cleaned or None
        fees=fees
        # Removed check_in_date, check_out_date
    )
    db.add(db_assignment)
    try:
        db.commit(); db.refresh(db_assignment)
        logger.info(f"Assigned student {student_id} to hostel '{hostel_name}', room '{room_number_cleaned}' (Record ID: {db_assignment.id})")
        return db_assignment
    except IntegrityError as e:
        db.rollback(); logger.error(f"DB integrity error assigning hostel: {e}")
        raise ValueError(f"Database error: Student might already be assigned a hostel room.")
    except Exception as e:
        db.rollback(); logger.error(f"Error committing hostel assignment: {e}");
        raise ValueError("Database error assigning hostel.")


def update_hostel_assignment(db: Session, assignment_id: int, update_data: Dict[str, Any]) -> Optional[models.Hostel]:
    """Updates an existing hostel assignment record."""
    db_assignment = get_hostel_assignment_by_id(db, assignment_id)
    if not db_assignment: return None

    updated = False

    if 'hostel_name' in update_data:
        new_hostel = update_data['hostel_name']
        if new_hostel not in HOSTEL_NAMES: raise ValueError("Invalid hostel name.")
        if db_assignment.hostel_name != new_hostel: db_assignment.hostel_name = new_hostel; updated = True

    if 'room_number' in update_data:
        new_room = update_data['room_number']
        new_room_cleaned = new_room.strip() if new_room else None # Allow setting to None/empty
        # if not new_room_cleaned: raise ValueError("Room number cannot be empty.") # Removed based on model
        if db_assignment.room_number != new_room_cleaned: db_assignment.room_number = new_room_cleaned; updated = True

    if 'fees' in update_data:
        new_fees = update_data['fees'] # Expected float or None
        if db_assignment.fees != new_fees: db_assignment.fees = new_fees; updated = True

    # Removed check_in_date and check_out_date updates

    if not updated:
        logger.debug(f"No actual changes detected for hostel assignment {assignment_id}.")
        return db_assignment # Return existing object if no changes

    try:
        db.add(db_assignment); db.commit(); db.refresh(db_assignment)
        logger.info(f"Updated hostel assignment {assignment_id}")
        return db_assignment
    except Exception as e:
        db.rollback(); logger.error(f"Error updating hostel assignment {assignment_id}: {e}");
        raise ValueError("Database error updating hostel assignment.")


def delete_hostel_assignment(db: Session, assignment_id: int) -> bool:
    """Deletes a hostel assignment record."""
    db_assignment = get_hostel_assignment_by_id(db, assignment_id)
    if not db_assignment: return False

    # Add checks here if needed before deletion (e.g., maybe check fees paid?)

    try:
        db.delete(db_assignment); db.commit()
        logger.info(f"Deleted hostel assignment {assignment_id} for student {db_assignment.student_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting hostel assignment {assignment_id}: {e}");
        raise ValueError("Database error deleting assignment.")