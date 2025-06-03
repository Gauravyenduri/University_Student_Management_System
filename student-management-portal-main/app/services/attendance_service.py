# app/services/attendance_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from app import models
from typing import List, Optional, Dict, Tuple
from datetime import date
import logging

logger = logging.getLogger(__name__)

# Removed get_enrolled_students_for_course, replaced by get_students_for_schedule

def get_students_for_schedule(db: Session, schedule_id: int) -> List[models.Student]:
    """Gets a list of students enrolled in the course associated with a specific schedule."""
    schedule = db.query(models.Schedule).filter(models.Schedule.id == schedule_id).first()
    if not schedule:
        return [] # Or raise error? Return empty list for now.
    # Find students enrolled in the course linked to this schedule
    return db.query(models.Student).join(models.Enrollment)\
        .filter(models.Enrollment.course_id == schedule.course_id)\
        .options(joinedload(models.Student.user)).order_by(models.Student.name).all()


def get_attendance_records(db: Session, schedule_id: int, attendance_date: date) -> Dict[int, models.AttendanceStatus]:
    """
    Gets existing attendance records for a specific schedule and date.
    Returns a dictionary mapping student_id to attendance status.
    """
    records = db.query(models.Attendance).filter(
        models.Attendance.schedule_id == schedule_id, # Changed from course_id
        models.Attendance.date == attendance_date
    ).all()
    # Create a dictionary for quick lookup: {student_id: status_enum}
    attendance_map = {record.student_id: record.status for record in records}
    return attendance_map

def save_attendance_records(
    db: Session,
    schedule_id: int, # Changed from course_id
    attendance_date: date,
    attendance_data: Dict[int, str] # Expects {student_id: status_string}
) -> Tuple[int, int]:
    """
    Saves or updates attendance records for a given schedule and date.
    Input dictionary format: { student_id: status_string (e.g., "PRESENT") }
    Returns a tuple: (records_created, records_updated)
    """
    logger.info(f"Saving attendance for schedule {schedule_id} on {attendance_date}")
    created_count = 0
    updated_count = 0

    # Get existing records for efficient update check
    existing_records = db.query(models.Attendance).filter(
        models.Attendance.schedule_id == schedule_id, # Changed from course_id
        models.Attendance.date == attendance_date
    ).all()
    existing_map = {record.student_id: record for record in existing_records}

    valid_statuses = {status.name for status in models.AttendanceStatus} # Set of valid enum names

    for student_id, status_str in attendance_data.items():
        # Validate status string
        if not status_str or status_str.upper() not in valid_statuses:
            logger.warning(f"Invalid status '{status_str}' provided for student {student_id}. Skipping.")
            continue # Skip invalid status entries

        status_enum = models.AttendanceStatus[status_str.upper()] # Convert string to enum member

        existing_record = existing_map.get(student_id)

        if existing_record:
            # Update existing record if status changed
            if existing_record.status != status_enum:
                logger.debug(f"Updating attendance for student {student_id} from {existing_record.status} to {status_enum}")
                existing_record.status = status_enum
                db.add(existing_record) # Add to session for update tracking
                updated_count += 1
        else:
            # Create new record
            logger.debug(f"Creating new attendance record for student {student_id} with status {status_enum}")
            new_record = models.Attendance(
                student_id=student_id,
                schedule_id=schedule_id, # Changed from course_id
                date=attendance_date,
                status=status_enum
            )
            db.add(new_record)
            created_count += 1

    try:
        db.commit()
        logger.info(f"Attendance saved: {created_count} created, {updated_count} updated.")
        return created_count, updated_count
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving attendance records for schedule {schedule_id}, date {attendance_date}: {e}", exc_info=True)
        raise ValueError("Database error saving attendance records.")

def get_attendance_for_student(
    db: Session,
    student_id: int,
    course_id: Optional[int] = None, # Changed back to course_id for student filtering
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[models.Attendance]:
    """
    Retrieves attendance records for a specific student, with optional filtering by course, start date, and end date.
    """
    logger.debug(f"Fetching attendance for student {student_id}, course {course_id}, start {start_date}, end {end_date}")
    query = db.query(models.Attendance).options(
        # Load schedule -> course for display
        joinedload(models.Attendance.schedule).joinedload(models.Schedule.course)
    ).filter(models.Attendance.student_id == student_id)

    # Join with Schedule to filter by course_id if provided
    if course_id:
        query = query.join(models.Schedule, models.Attendance.schedule_id == models.Schedule.id)\
                     .filter(models.Schedule.course_id == course_id) # Filter on the joined Schedule table

    if start_date:
        query = query.filter(models.Attendance.date >= start_date)
    if end_date:
        query = query.filter(models.Attendance.date <= end_date)

    # Order by date descending, then schedule details (e.g., course name via schedule)
    query = query.join(models.Schedule, models.Attendance.schedule_id == models.Schedule.id)\
                 .join(models.Course, models.Schedule.course_id == models.Course.id)\
                 .order_by(models.Attendance.date.desc(), models.Course.name, models.Schedule.start_time)

    results = query.all()
    logger.debug(f"Found {len(results)} attendance records for student {student_id}")
    return results
