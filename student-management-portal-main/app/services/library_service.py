# app/services/library_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

# === Library Borrowing Record Management ===

def get_all_library_records(db: Session, student_id: Optional[int] = None) -> List[models.Library]:
    """Retrieves all library borrowing records, optionally filtered by student."""
    query = db.query(models.Library).options(
        joinedload(models.Library.student).joinedload(models.Student.user) # Load student -> user
    )
    if student_id:
        query = query.filter(models.Library.student_id == student_id)
    # Order by student name, then handle NULL dates in MySQL-compatible way
    query = query.join(models.Student).order_by(
        models.Student.name,
        func.IF(models.Library.borrowed_date.is_(None), 1, 0),
        models.Library.borrowed_date.desc()
    )
    return query.all()

def get_library_record_by_id(db: Session, record_id: int) -> Optional[models.Library]:
    """Retrieves a single library borrowing record by its ID."""
    return db.query(models.Library).options(
        joinedload(models.Library.student).joinedload(models.Student.user)
    ).filter(models.Library.id == record_id).first()

# Maybe get record by student ID? A student might have multiple records if model is used differently.
# Let's assume one main record per student for now based on the model structure.
def get_library_record_by_student_id(db: Session, student_id: int) -> Optional[models.Library]:
     return db.query(models.Library).filter(models.Library.student_id == student_id).first()


def create_library_record(db: Session, student_id: int, books_borrowed: int,
                           borrowed_date: Optional[date], return_date: Optional[date]) -> models.Library:
    """Creates a new library borrowing record for a student."""
    # Check if student exists
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student with ID {student_id} not found.")

    # Check if a record already exists for this student (if only one allowed)
    existing_record = get_library_record_by_student_id(db, student_id)
    if existing_record:
        raise ValueError(f"A library record already exists for student '{student.name}'. Please edit the existing record.")

    if books_borrowed < 0: raise ValueError("Books borrowed cannot be negative.")

    db_record = models.Library(
        student_id=student_id,
        books_borrowed=books_borrowed,
        borrowed_date=borrowed_date,
        return_date=return_date
    )
    db.add(db_record)
    try:
        db.commit(); db.refresh(db_record)
        logger.info(f"Created library record {db_record.id} for student {student_id}")
        return db_record
    except Exception as e:
        db.rollback(); logger.error(f"Error creating library record: {e}");
        raise ValueError("Database error creating library record.")


def update_library_record(db: Session, record_id: int, update_data: Dict[str, Any]) -> Optional[models.Library]:
    """Updates an existing library borrowing record."""
    db_record = get_library_record_by_id(db, record_id)
    if not db_record: return None

    updated = False
    # Note: student_id should generally not be changed on an existing record.

    if 'books_borrowed' in update_data:
        borrowed = update_data['books_borrowed'] # Expected int
        if borrowed is None or borrowed < 0: raise ValueError("Books borrowed must be 0 or more.")
        if db_record.books_borrowed != borrowed: db_record.books_borrowed = borrowed; updated = True

    if 'borrowed_date' in update_data:
        b_date = update_data['borrowed_date'] # Expected date or None
        if db_record.borrowed_date != b_date: db_record.borrowed_date = b_date; updated = True

    if 'return_date' in update_data:
        r_date = update_data['return_date'] # Expected date or None
        # Add validation: return date cannot be before borrow date?
        if b_date and r_date and r_date < b_date:
             raise ValueError("Return date cannot be before the borrowed date.")
        if db_record.return_date != r_date: db_record.return_date = r_date; updated = True

    if not updated: return db_record

    try:
        db.add(db_record); db.commit(); db.refresh(db_record)
        logger.info(f"Updated library record {record_id}")
        return db_record
    except Exception as e:
        db.rollback(); logger.error(f"Error updating library record {record_id}: {e}");
        raise ValueError("Database error updating library record.")


def delete_library_record(db: Session, record_id: int) -> bool:
    """Deletes a library borrowing record."""
    db_record = get_library_record_by_id(db, record_id)
    if not db_record: return False

    # Add checks if needed (e.g., cannot delete if books_borrowed > 0?)
    # if db_record.books_borrowed > 0:
    #    raise ValueError("Cannot delete record while books are still marked as borrowed.")

    try:
        db.delete(db_record); db.commit()
        logger.info(f"Deleted library record {record_id} for student {db_record.student_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting library record {record_id}: {e}");
        raise ValueError("Database error deleting library record.")