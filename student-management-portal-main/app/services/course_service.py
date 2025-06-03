# app/services/course_service.py

from sqlalchemy.orm import Session, joinedload # Import joinedload
from sqlalchemy import func, or_ # Import or_ for dependency checks
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_courses(db: Session) -> List[models.Course]:
    """Retrieves all course records, eager loading department."""
    return db.query(models.Course).options(
        joinedload(models.Course.department) # Eager load department
    ).order_by(models.Course.name).all()

def get_course_by_id(db: Session, course_id: int) -> Optional[models.Course]:
    """Retrieves a single course by ID, eager loading department."""
    return db.query(models.Course).options(
        joinedload(models.Course.department) # Eager load department
    ).filter(models.Course.id == course_id).first()

def get_course_by_name(db: Session, name: str, department_id: int) -> Optional[models.Course]:
    """Retrieves a course by name within a specific department (case-insensitive)."""
    # Course names only need to be unique within a department now
    return db.query(models.Course).filter(
        func.lower(models.Course.name) == func.lower(name),
        models.Course.department_id == department_id
    ).first()

def create_course(db: Session, name: str, department_id: int, credits: Optional[int], description: Optional[str]) -> models.Course:
    """Creates a new course, assigning it to a department."""
    # Check if department exists
    department = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not department:
        raise ValueError(f"Department with ID {department_id} not found.")

    # Check uniqueness within the department
    existing_course = get_course_by_name(db, name, department_id)
    if existing_course:
        raise ValueError(f"Course with name '{name}' already exists in department '{department.name}'.")

    db_course = models.Course(
        name=name,
        credits=credits,
        description=description,
        department_id=department_id # Assign mandatory department
    )
    db.add(db_course)
    try:
        db.commit()
        db.refresh(db_course)
        return db_course
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating course: {e}")
        raise ValueError("Database error creating course. Name might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing course creation: {e}", exc_info=True)
        raise ValueError("Failed to create course record due to database error.")

def update_course(db: Session, course_id: int, update_data: Dict[str, Any]) -> Optional[models.Course]:
    """Updates an existing course."""
    db_course = get_course_by_id(db, course_id)
    if not db_course:
        return None # Not found

    # --- Department Update ---
    new_department_id = update_data.get('department_id')
    if new_department_id is None: # Should be mandatory based on model
         raise ValueError("Department ID is required.")
    if new_department_id != db_course.department_id:
        # Check if the new department exists
        new_department = db.query(models.Department).filter(models.Department.id == new_department_id).first()
        if not new_department:
            raise ValueError(f"Department with ID {new_department_id} not found.")
        # Check for name conflict in the *new* department before changing
        new_name_for_check = update_data.get('name', db_course.name) # Use new name if provided, else current
        existing_in_new_dept = get_course_by_name(db, new_name_for_check, new_department_id)
        if existing_in_new_dept and existing_in_new_dept.id != course_id:
             raise ValueError(f"Course name '{new_name_for_check}' already exists in the target department '{new_department.name}'.")
        db_course.department_id = new_department_id

    # --- Name Update (check uniqueness within the potentially new department) ---
    new_name = update_data.get('name')
    # Check if name changed OR department changed (need to re-validate uniqueness)
    if new_name and (func.lower(new_name) != func.lower(db_course.name) or new_department_id != db_course.department_id):
        # Validate against the final department ID
        final_department_id = new_department_id if new_department_id is not None else db_course.department_id
        existing_course = get_course_by_name(db, new_name, final_department_id)
        if existing_course and existing_course.id != course_id:
            # Fetch department name for error message if needed
            dept_name = db.query(models.Department.name).filter(models.Department.id == final_department_id).scalar() or "target"
            raise ValueError(f"Course name '{new_name}' is already in use in the {dept_name} department.")
        db_course.name = new_name

    # --- Credits Update ---
    if 'credits' in update_data:
        # Allow setting credits to None or a new value
        db_course.credits = update_data['credits'] # Assumes value is already Int or None

    # Update Description (handle if key exists)
    if 'description' in update_data:
        db_course.description = update_data['description']

    try:
        db.add(db_course)
        db.commit()
        db.refresh(db_course)
        return db_course
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating course {course_id}: {e}")
        raise ValueError("Database error updating course. Name might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing course update {course_id}: {e}", exc_info=True)
        raise ValueError("Failed to update course record due to database error.")

def delete_course(db: Session, course_id: int) -> bool:
    """Deletes a course, checking for dependencies first."""
    db_course = get_course_by_id(db, course_id)
    if not db_course:
        return False # Not found

    # --- Dependency Checks ---
    # Check enrollments, schedules, grades, attendance, exams
    dependencies = db.query(models.Enrollment.id).filter(models.Enrollment.course_id == course_id).first() or \
                   db.query(models.Schedule.id).filter(models.Schedule.course_id == course_id).first() or \
                   db.query(models.Exam.id).filter(models.Exam.course_id == course_id).first()

    if dependencies:
        logger.warning(f"Attempted to delete course {course_id} ('{db_course.name}') which still has related records (enrollments, schedules, exams).")
        raise ValueError(f"Cannot delete course '{db_course.name}' because it is still referenced by enrollments, schedules, or exams. Remove these references first.")
    # --- End Dependency Checks ---

    try:
        db.delete(db_course)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting course {course_id}: {e}", exc_info=True)
        # Re-raise a specific error or return False
        raise ValueError("Failed to delete course due to a database error.")
        # return False