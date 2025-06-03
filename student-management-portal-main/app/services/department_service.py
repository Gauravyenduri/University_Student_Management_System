# app/services/department_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func # For case-insensitive check
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_departments(db: Session) -> List[models.Department]:
    """Retrieves all department records, loading HoD instructor info."""
    return db.query(models.Department).options(
        joinedload(models.Department.hod_instructor).joinedload(models.Instructor.user) # Load HoD -> User too
    ).order_by(models.Department.name).all()

def get_department_by_id(db: Session, department_id: int) -> Optional[models.Department]:
    """Retrieves a single department by ID, loading HoD instructor."""
    return db.query(models.Department).options(
        joinedload(models.Department.hod_instructor) # Eager load HoD
    ).filter(models.Department.id == department_id).first()

def get_department_by_name(db: Session, name: str) -> Optional[models.Department]:
    """Retrieves a department by name (case-insensitive)."""
    return db.query(models.Department).filter(func.lower(models.Department.name) == func.lower(name)).first()

def create_department(db: Session, name: str) -> models.Department:
    """Creates a new department. HoD is set via update."""
    existing_dept = get_department_by_name(db, name)
    if existing_dept:
        raise ValueError(f"Department with name '{name}' already exists.")

    # HoD is not set during creation anymore
    db_department = models.Department(name=name, head_of_department_id=None)
    db.add(db_department)
    try:
        db.commit()
        db.refresh(db_department)
        return db_department
    except IntegrityError as e:
         db.rollback()
         logger.error(f"Database integrity error creating department: {e}")
         raise ValueError("Database error creating department. Name might already exist.")
    except Exception as e:
         db.rollback()
         logger.error(f"Error committing department creation: {e}", exc_info=True)
         raise ValueError("Failed to create department record due to database error.")


def update_department(db: Session, department_id: int, update_data: Dict[str, Any]) -> Optional[models.Department]:
    """Updates an existing department, including potentially the HoD."""
    db_department = get_department_by_id(db, department_id)
    if not db_department:
        return None

    # Handle name update (check uniqueness)
    new_name = update_data.get('name')
    if new_name and func.lower(new_name) != func.lower(db_department.name):
        existing_dept = get_department_by_name(db, new_name)
        if existing_dept and existing_dept.id != department_id:
            raise ValueError(f"Department name '{new_name}' is already in use.")
        db_department.name = new_name

    # Handle HoD update
    if 'head_of_department_id' in update_data:
        new_hod_id = update_data['head_of_department_id']
        if new_hod_id is not None:
            # Validate the chosen Instructor ID
            hod_instructor = db.query(models.Instructor).filter(models.Instructor.id == new_hod_id).first()
            if not hod_instructor:
                raise ValueError(f"Instructor with ID {new_hod_id} not found.")
            # --- Optional Business Rule Validation ---
            # if hod_instructor.department_id != department_id:
            #     raise ValueError(f"Instructor '{hod_instructor.name}' does not belong to the '{db_department.name}' department.")
            # --- End Optional Validation ---
            db_department.head_of_department_id = new_hod_id
        else:
            # Allow setting HoD to None
            db_department.head_of_department_id = None

    try:
        db.add(db_department)
        db.commit()
        db.refresh(db_department)
        # Ensure HoD relationship is refreshed
        if db_department.head_of_department_id:
            db.refresh(db_department.hod_instructor)
        return db_department
    except IntegrityError as e:
         db.rollback()
         logger.error(f"Database integrity error updating department {department_id}: {e}")
         raise ValueError("Database error updating department. Name might already exist.")
    except Exception as e:
         db.rollback()
         logger.error(f"Error committing department update {department_id}: {e}", exc_info=True)
         raise ValueError("Failed to update department record due to database error.")

def delete_department(db: Session, department_id: int) -> bool:
    """Deletes a department."""
    db_department = get_department_by_id(db, department_id)
    if not db_department:
        return False # Department not found

    # Check if any instructors are assigned to this department BEFORE deleting
    instructor_count = db.query(models.Instructor).filter(models.Instructor.department_id == department_id).count()
    if instructor_count > 0:
        logger.warning(f"Attempted to delete department {department_id} ('{db_department.name}') which still has {instructor_count} instructor(s) assigned.")
        raise ValueError(f"Cannot delete department '{db_department.name}' because it still has instructors assigned to it. Reassign instructors first.")
        # Alternatively, you could handle this by setting instructor.department_id to NULL
        # if the FK constraint allows it, but raising an error is usually safer.

    try:
        db.delete(db_department)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        # Check for Foreign Key constraint errors specifically if needed
        logger.error(f"Error deleting department {department_id}: {e}", exc_info=True)
        # Re-raise or return False based on error type
        # Could potentially still fail if other entities depend on it (e.g., Courses if linked)
        raise ValueError("Failed to delete department due to a database error or dependency.")
        # return False