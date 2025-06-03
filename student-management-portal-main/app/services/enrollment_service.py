# app/services/enrollment_service.py
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

def get_enrollments_for_student(db: Session, student_id: int) -> List[models.Enrollment]:
    """Fetches all enrollments for a given student, loading the course."""
    return db.query(models.Enrollment).options(
        joinedload(models.Enrollment.course) # Eager load course details
    ).filter(models.Enrollment.student_id == student_id).order_by(models.Enrollment.enrollment_date.desc()).all()

def get_available_courses_for_student(db: Session, student_id: int) -> List[models.Course]:
    """Fetches courses the student is NOT currently enrolled in."""
    # Get IDs of courses the student IS enrolled in
    enrolled_course_ids = db.query(models.Enrollment.course_id).filter(
        models.Enrollment.student_id == student_id
    ).subquery()

    # Query courses whose IDs are NOT in the subquery
    available_courses = db.query(models.Course).filter(
        models.Course.id.notin_(enrolled_course_ids)
    ).order_by(models.Course.name).all()
    # TODO: Add more filtering later (prerequisites, program requirements, capacity?)
    return available_courses

def create_enrollment(db: Session, student_id: int, course_id: int) -> models.Enrollment:
    """Enrolls a student in a course."""
    # Check if student/course exist
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student: raise ValueError("Student not found.")
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course: raise ValueError("Course not found.")

    # Check if already enrolled
    existing_enrollment = db.query(models.Enrollment).filter_by(student_id=student_id, course_id=course_id).first()
    if existing_enrollment:
        raise ValueError(f"Already enrolled in course '{course.name}'.")

    # TODO: Add checks for enrollment capacity, prerequisites, time conflicts, etc.

    db_enrollment = models.Enrollment(student_id=student_id, course_id=course_id)
    db.add(db_enrollment)
    try:
        db.commit()
        db.refresh(db_enrollment)
        logger.info(f"Student {student_id} enrolled in course {course_id}")
        return db_enrollment
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating enrollment for student {student_id}, course {course_id}: {e}", exc_info=True)
        raise ValueError("Database error during enrollment.")


def delete_enrollment(db: Session, enrollment_id: int, student_id: int) -> bool:
    """Unenrolls a student by enrollment ID, ensuring ownership."""
    db_enrollment = db.query(models.Enrollment).filter(
        models.Enrollment.id == enrollment_id,
        models.Enrollment.student_id == student_id # IMPORTANT: Ensure student owns this enrollment
    ).first()

    if not db_enrollment:
        return False # Not found or doesn't belong to the student

    # TODO: Add checks if unenrollment is allowed (e.g., before a certain date?)

    try:
        db.delete(db_enrollment)
        db.commit()
        logger.info(f"Student {student_id} unenrolled from enrollment {enrollment_id}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting enrollment {enrollment_id} for student {student_id}: {e}", exc_info=True)
        raise ValueError("Database error during unenrollment.")