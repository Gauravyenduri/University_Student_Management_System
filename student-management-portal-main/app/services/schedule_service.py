# app/services/schedule_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_all_schedules(db: Session) -> List[models.Schedule]:
    """Retrieves all schedule records, loading related entities."""
    return db.query(models.Schedule).options(
        joinedload(models.Schedule.course),
        joinedload(models.Schedule.instructor).joinedload(models.Instructor.user), # Instructor -> User
        joinedload(models.Schedule.classroom)
    ).order_by(models.Schedule.day_of_week, models.Schedule.start_time).all() # Example ordering

def get_schedule_by_id(db: Session, schedule_id: int) -> Optional[models.Schedule]:
    """Retrieves a single schedule by ID, loading related entities."""
    return db.query(models.Schedule).options(
        joinedload(models.Schedule.course),
        joinedload(models.Schedule.instructor).joinedload(models.Instructor.user),
        joinedload(models.Schedule.classroom)
    ).filter(models.Schedule.id == schedule_id).first()

def validate_foreign_keys(db: Session, course_id: int, instructor_id: int, classroom_id: Optional[int]):
    """Helper to check if related entities exist."""
    if not db.query(models.Course).filter(models.Course.id == course_id).first():
        raise ValueError(f"Course with ID {course_id} not found.")
    if not db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first():
        raise ValueError(f"Instructor with ID {instructor_id} not found.")
    if classroom_id and not db.query(models.Classroom).filter(models.Classroom.id == classroom_id).first():
        raise ValueError(f"Classroom with ID {classroom_id} not found.")
    # Add potential conflict checks here later (e.g., instructor/classroom availability)

def create_schedule(
    db: Session,
    course_id: int,
    instructor_id: int,
    classroom_id: Optional[int],
    day_of_week: str,
    start_time: str, # Assuming time is stored as string for simplicity
    end_time: str
) -> models.Schedule:
    """Creates a new schedule."""
    # Validate FKs first
    validate_foreign_keys(db, course_id, instructor_id, classroom_id)

    # Basic validation for day/time format could be added here if needed

    db_schedule = models.Schedule(
        course_id=course_id,
        instructor_id=instructor_id,
        classroom_id=classroom_id, # Can be None
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time
    )
    db.add(db_schedule)
    try:
        db.commit()
        db.refresh(db_schedule)
        return db_schedule
    except IntegrityError as e: # Catch potential DB constraint issues
        db.rollback()
        logger.error(f"Database integrity error creating schedule: {e}")
        raise ValueError("Database error creating schedule.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing schedule creation: {e}", exc_info=True)
        raise ValueError("Failed to create schedule record due to database error.")

def update_schedule(db: Session, schedule_id: int, update_data: Dict[str, Any]) -> Optional[models.Schedule]:
    """Updates an existing schedule."""
    db_schedule = get_schedule_by_id(db, schedule_id)
    if not db_schedule:
        return None # Not found

    # Extract potential changes
    course_id = update_data.get('course_id', db_schedule.course_id)
    instructor_id = update_data.get('instructor_id', db_schedule.instructor_id)
    classroom_id = update_data.get('classroom_id', db_schedule.classroom_id) # Can be None

    # Validate FKs if they changed
    if (course_id != db_schedule.course_id or
        instructor_id != db_schedule.instructor_id or
        classroom_id != db_schedule.classroom_id):
         validate_foreign_keys(db, course_id, instructor_id, classroom_id)

    # Update fields
    db_schedule.course_id = course_id
    db_schedule.instructor_id = instructor_id
    db_schedule.classroom_id = classroom_id
    db_schedule.day_of_week = update_data.get('day_of_week', db_schedule.day_of_week)
    db_schedule.start_time = update_data.get('start_time', db_schedule.start_time)
    db_schedule.end_time = update_data.get('end_time', db_schedule.end_time)

    try:
        db.add(db_schedule)
        db.commit()
        db.refresh(db_schedule)
        # Refresh relationships after commit
        db.refresh(db_schedule.course)
        db.refresh(db_schedule.instructor)
        if db_schedule.classroom: db.refresh(db_schedule.classroom)
        return db_schedule
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating schedule {schedule_id}: {e}")
        raise ValueError("Database error updating schedule.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing schedule update {schedule_id}: {e}", exc_info=True)
        raise ValueError("Failed to update schedule record due to database error.")

def delete_schedule(db: Session, schedule_id: int) -> bool:
    """Deletes a schedule."""
    db_schedule = get_schedule_by_id(db, schedule_id)
    if not db_schedule:
        return False # Not found

    # --- Dependency Check: Attendance ---
    attendance_exists = db.query(models.Attendance.id).filter(models.Attendance.schedule_id == schedule_id).first()
    if attendance_exists:
        logger.warning(f"Attempted to delete schedule {schedule_id} which has existing attendance records.")
        raise ValueError("Cannot delete schedule with existing attendance records. Please remove attendance data first.")
    # --- End Dependency Check ---

    try:
        db.delete(db_schedule)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting schedule {schedule_id}: {e}", exc_info=True)
        raise ValueError("Failed to delete schedule due to a database error.")
