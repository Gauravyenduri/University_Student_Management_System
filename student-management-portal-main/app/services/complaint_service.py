# app/services/complaint_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from app import models
from typing import List, Optional, Dict, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

# === Student Complaint Management ===

def get_complaints_for_student(db: Session, student_id: int) -> List[models.Complaint]:
    """Retrieves all complaints filed by a specific student."""
    logger.debug(f"Fetching complaints for student {student_id}")
    return db.query(models.Complaint)\
        .filter(models.Complaint.student_id == student_id)\
        .options(joinedload(models.Complaint.student)).order_by(desc(models.Complaint.date), desc(models.Complaint.created_at))\
        .all()

def get_student_complaint_by_id(db: Session, complaint_id: int, student_id: int) -> Optional[models.Complaint]:
    """Retrieves a single complaint by its ID, ensuring it belongs to the student."""
    logger.debug(f"Fetching complaint {complaint_id} for student {student_id}")
    return db.query(models.Complaint).filter(
        models.Complaint.id == complaint_id,
        models.Complaint.student_id == student_id # Ownership check
    ).first()

def create_complaint(db: Session, student_id: int, description: str) -> models.Complaint:
    """Creates a new complaint record for a student."""
    # 1. Check student exists (though usually guaranteed by logged-in user)
    if not db.query(models.Student.id).filter(models.Student.id == student_id).first():
        raise ValueError("Student profile not found.")

    # 2. Validate description
    if not description or not description.strip():
        raise ValueError("Complaint description cannot be empty.")

    # 3. Create record (defaults status to OPEN, date to today)
    db_complaint = models.Complaint(
        student_id=student_id,
        description=description.strip()
        # Status and date have defaults in the model
    )
    db.add(db_complaint)
    try:
        db.commit(); db.refresh(db_complaint)
        logger.info(f"Created complaint {db_complaint.id} for student {student_id}")
        return db_complaint
    except Exception as e:
        db.rollback(); logger.error(f"Error creating complaint for student {student_id}: {e}");
        raise ValueError("Database error creating complaint.")


def update_student_complaint(db: Session, complaint_id: int, student_id: int, description: str) -> Optional[models.Complaint]:
    """Updates the description of an existing complaint owned by the student."""
    # Students likely should only update description, not status or resolution.
    # Only allow updates if status is still OPEN? Business rule.
    db_complaint = get_student_complaint_by_id(db, complaint_id, student_id) # Check ownership
    if not db_complaint: return None

    # Check if editable (e.g., only if status is OPEN)
    if db_complaint.status != models.ComplaintStatus.OPEN:
         raise ValueError(f"Cannot update complaint as its status is '{db_complaint.status.value}'.")

    # Validate new description
    if not description or not description.strip():
        raise ValueError("Complaint description cannot be empty.")

    new_description = description.strip()
    if db_complaint.description == new_description:
        logger.debug(f"No change in description for complaint {complaint_id}.")
        return db_complaint # No actual update needed

    db_complaint.description = new_description
    # updated_at timestamp will be handled automatically by onupdate

    try:
        db.add(db_complaint); db.commit(); db.refresh(db_complaint)
        logger.info(f"Student {student_id} updated complaint {complaint_id}")
        return db_complaint
    except Exception as e:
        db.rollback(); logger.error(f"Error updating complaint {complaint_id}: {e}");
        raise ValueError("Database error updating complaint.")


def delete_student_complaint(db: Session, complaint_id: int, student_id: int) -> bool:
    """Deletes a complaint record owned by the student."""
    # Only allow deletion if status is OPEN? Business rule.
    db_complaint = get_student_complaint_by_id(db, complaint_id, student_id) # Check ownership
    if not db_complaint: return False

    # Check if deletable (e.g., only if status is OPEN)
    if db_complaint.status != models.ComplaintStatus.OPEN:
         raise ValueError(f"Cannot delete complaint as its status is '{db_complaint.status.value}'.")

    try:
        db.delete(db_complaint); db.commit()
        logger.info(f"Student {student_id} deleted complaint {complaint_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting complaint {complaint_id}: {e}");
        raise ValueError("Database error deleting complaint.")

# --- Admin functions for viewing/updating status/resolution would go here or in admin service ---
def admin_update_complaint_status(db: Session, complaint_id: int, new_status: models.ComplaintStatus, resolution: Optional[str] = None) -> Optional[models.Complaint]:
    """Allows an authorized user (admin/staff) to update status and resolution."""
    # NOTE: This function needs proper permission checks in the route calling it.
    db_complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not db_complaint: return None
    updated = False
    if db_complaint.status != new_status:
        db_complaint.status = new_status; updated = True
    if resolution is not None and db_complaint.resolution != resolution:
        db_complaint.resolution = resolution; updated = True

    if not updated: return db_complaint
    try:
        db.add(db_complaint); db.commit(); db.refresh(db_complaint)
        logger.info(f"Complaint {complaint_id} status/resolution updated.")
        return db_complaint
    except Exception as e:
        db.rollback(); logger.error(f"Error updating complaint status {complaint_id}: {e}")
        raise ValueError("Database error updating complaint status.")

def admin_get_all_complaints(
    db: Session,
    status: Optional[str] = None,
    student_id: Optional[int] = None
) -> List[models.Complaint]:
    """Retrieves all complaints, optionally filtered by status or student (for Admin)."""
    logger.debug(f"ADMIN: Fetching all complaints. Filters: status={status}, student_id={student_id}")
    query = db.query(models.Complaint).options(
        joinedload(models.Complaint.student).joinedload(models.Student.user) # Load student details
    )

    if student_id:
        query = query.filter(models.Complaint.student_id == student_id)
    if status and status in models.ComplaintStatus.__members__: # Filter by valid status enum NAME
         query = query.filter(models.Complaint.status == models.ComplaintStatus[status])

    # Order by status (e.g., Open first), then date descending
    query = query.order_by(
        models.Complaint.status, # Default enum order might work, or use CASE
        desc(models.Complaint.date),
        desc(models.Complaint.created_at)
    )
    return query.all()

def admin_get_complaint_by_id(db: Session, complaint_id: int) -> Optional[models.Complaint]:
    """Retrieves a single complaint by ID for Admin view."""
    # Loads student details for context
    return db.query(models.Complaint).options(
        joinedload(models.Complaint.student).joinedload(models.Student.user)
    ).filter(models.Complaint.id == complaint_id).first()


def admin_update_complaint(
    db: Session,
    complaint_id: int,
    new_status_str: str, # Status NAME as string (e.g., "RESOLVED", "CLOSED")
    resolution_note: Optional[str] = None
    ) -> Optional[models.Complaint]:
    """
    Allows an Admin/authorized user to update the status and add a resolution note.
    """
    logger.info(f"ADMIN: Attempting to update complaint {complaint_id} to status '{new_status_str}'")
    db_complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not db_complaint:
        logger.warning(f"ADMIN: Complaint {complaint_id} not found for update.")
        return None

    # Validate new status string
    try:
        new_status_enum = models.ComplaintStatus[new_status_str.upper()]
    except KeyError:
        raise ValueError(f"Invalid status value provided: '{new_status_str}'.")

    updated = False
    if db_complaint.status != new_status_enum:
        db_complaint.status = new_status_enum
        logger.debug(f"ADMIN: Updating complaint {complaint_id} status to {new_status_enum.name}")
        updated = True

    # Update resolution note if provided (allow clearing it by passing empty string?)
    if resolution_note is not None:
        cleaned_resolution = resolution_note.strip() if resolution_note else None
        if db_complaint.resolution != cleaned_resolution:
             db_complaint.resolution = cleaned_resolution
             logger.debug(f"ADMIN: Updating complaint {complaint_id} resolution note.")
             updated = True

    if not updated:
        logger.debug(f"ADMIN: No changes detected for complaint {complaint_id}.")
        return db_complaint # Return existing if no change

    try:
        db.add(db_complaint)
        db.commit()
        db.refresh(db_complaint)
        logger.info(f"ADMIN: Complaint {complaint_id} updated successfully. New status: {db_complaint.status.name}")
        return db_complaint
    except Exception as e:
        db.rollback()
        logger.error(f"ADMIN: Error committing complaint update {complaint_id}: {e}", exc_info=True)
        raise ValueError("Database error updating complaint status/resolution.")

# Note: Admin delete might be different from student delete (e.g., allow deleting resolved/closed?)
# For now, we can reuse the student delete or create admin_delete_complaint if rules differ.
# Let's assume admin can delete any record for now.
def admin_delete_complaint(db: Session, complaint_id: int) -> bool:
    """Deletes any complaint record (Admin action)."""
    db_complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not db_complaint: return False
    try:
        db.delete(db_complaint); db.commit()
        logger.info(f"ADMIN: Deleted complaint {complaint_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting complaint {complaint_id} by admin: {e}");
        raise ValueError("Database error deleting complaint.")