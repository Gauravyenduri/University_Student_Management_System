# app/services/classroom_service.py

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_classrooms(db: Session) -> List[models.Classroom]:
    """Retrieves all classroom records."""
    return db.query(models.Classroom).order_by(models.Classroom.location).all()

def get_classroom_by_id(db: Session, classroom_id: int) -> Optional[models.Classroom]:
    """Retrieves a single classroom by ID."""
    return db.query(models.Classroom).filter(models.Classroom.id == classroom_id).first()

def get_classroom_by_location(db: Session, location: str) -> Optional[models.Classroom]:
    """Retrieves a classroom by location (case-insensitive)."""
    return db.query(models.Classroom).filter(func.lower(models.Classroom.location) == func.lower(location)).first()

def create_classroom(db: Session, location: str, capacity: Optional[int]) -> models.Classroom:
    """Creates a new classroom."""
    existing_classroom = get_classroom_by_location(db, location)
    if existing_classroom:
        raise ValueError(f"Classroom with location '{location}' already exists.")

    db_classroom = models.Classroom(
        location=location,
        capacity=capacity
    )
    db.add(db_classroom)
    try:
        db.commit()
        db.refresh(db_classroom)
        return db_classroom
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating classroom: {e}")
        raise ValueError("Database error creating classroom. Location might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing classroom creation: {e}", exc_info=True)
        raise ValueError("Failed to create classroom record due to database error.")

def update_classroom(db: Session, classroom_id: int, update_data: Dict[str, Any]) -> Optional[models.Classroom]:
    """Updates an existing classroom."""
    db_classroom = get_classroom_by_id(db, classroom_id)
    if not db_classroom:
        return None # Not found

    # Update Location (with uniqueness check)
    new_location = update_data.get('location')
    if new_location and func.lower(new_location) != func.lower(db_classroom.location):
        existing_classroom = get_classroom_by_location(db, new_location)
        if existing_classroom and existing_classroom.id != classroom_id:
            raise ValueError(f"Classroom location '{new_location}' is already in use.")
        db_classroom.location = new_location

    # Update Capacity (handle if key exists)
    if 'capacity' in update_data:
        db_classroom.capacity = update_data['capacity'] # Assumes value is Int or None

    try:
        db.add(db_classroom)
        db.commit()
        db.refresh(db_classroom)
        return db_classroom
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating classroom {classroom_id}: {e}")
        raise ValueError("Database error updating classroom. Location might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing classroom update {classroom_id}: {e}", exc_info=True)
        raise ValueError("Failed to update classroom record due to database error.")

def delete_classroom(db: Session, classroom_id: int) -> bool:
    """Deletes a classroom, checking for dependencies first."""
    db_classroom = get_classroom_by_id(db, classroom_id)
    if not db_classroom:
        return False # Not found

    # Dependency Check: Check if any schedules use this classroom
    schedule_exists = db.query(models.Schedule.id).filter(models.Schedule.classroom_id == classroom_id).first()
    if schedule_exists:
        logger.warning(f"Attempted to delete classroom {classroom_id} ('{db_classroom.location}') which is used in schedules.")
        raise ValueError(f"Cannot delete classroom '{db_classroom.location}' because it is currently assigned to one or more schedules. Remove it from schedules first.")

    try:
        db.delete(db_classroom)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting classroom {classroom_id}: {e}", exc_info=True)
        raise ValueError("Failed to delete classroom due to a database error or dependency.")