# app/services/club_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# === Club Definition Management ===

def get_all_clubs(db: Session) -> List[models.Club]:
    """Retrieves all defined clubs."""
    return db.query(models.Club).order_by(models.Club.name).all()

def get_club_by_id(db: Session, club_id: int) -> Optional[models.Club]:
    """Retrieves a single club by ID."""
    return db.query(models.Club).filter(models.Club.id == club_id).first()

def get_club_by_name(db: Session, name: str) -> Optional[models.Club]:
    """Retrieves a club by name (case-insensitive)."""
    return db.query(models.Club).filter(func.lower(models.Club.name) == func.lower(name)).first()

def create_club(db: Session, name: str, club_type: Optional[str], description: Optional[str]) -> models.Club:
    """Creates a new club definition."""
    if not name or not name.strip():
        raise ValueError("Club name is required.")
    name = name.strip()

    # Check for duplicate name
    existing_club = get_club_by_name(db, name)
    if existing_club:
        raise ValueError(f"A club named '{name}' already exists.")

    db_club = models.Club(
        name=name,
        type=club_type.strip() if club_type else None,
        description=description.strip() if description else None
        # Set defaults for other fields like advisor_id, is_active if added to model
    )
    db.add(db_club)
    try:
        db.commit()
        db.refresh(db_club)
        logger.info(f"Created club '{name}' (ID: {db_club.id})")
        return db_club
    except IntegrityError as e: # Catch unique name constraint error
        db.rollback()
        logger.error(f"DB integrity error creating club: {e}")
        raise ValueError(f"Database error: A club named '{name}' might already exist.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing club creation: {e}", exc_info=True)
        raise ValueError("Failed to create club due to a database error.")


def update_club(db: Session, club_id: int, update_data: Dict[str, Any]) -> Optional[models.Club]:
    """Updates an existing club definition."""
    db_club = get_club_by_id(db, club_id)
    if not db_club:
        return None # Not found

    updated = False

    # Update Name (with uniqueness check)
    if 'name' in update_data:
        new_name = update_data['name'].strip()
        if not new_name: raise ValueError("Club name cannot be empty.")
        if func.lower(new_name) != func.lower(db_club.name):
             # Check if the new name is already taken by *another* club
             existing_club = get_club_by_name(db, new_name)
             if existing_club and existing_club.id != club_id:
                 raise ValueError(f"Club name '{new_name}' is already in use.")
             db_club.name = new_name
             updated = True

    # Update Type
    if 'type' in update_data:
        new_type = update_data['type'].strip() if update_data['type'] else None
        if db_club.type != new_type: db_club.type = new_type; updated = True

    # Update Description
    if 'description' in update_data:
        new_desc = update_data['description'].strip() if update_data['description'] else None
        if db_club.description != new_desc: db_club.description = new_desc; updated = True

    # Update other optional fields (advisor, is_active) if they exist in model/update_data

    if not updated: return db_club # No changes

    try:
        db.add(db_club); db.commit(); db.refresh(db_club)
        logger.info(f"Updated club {club_id} ('{db_club.name}')")
        return db_club
    except IntegrityError as e: db.rollback(); logger.error(...); raise ValueError("DB error updating club. Name might conflict.")
    except Exception as e: db.rollback(); logger.error(...); raise ValueError("DB error updating club.")


def delete_club(db: Session, club_id: int) -> bool:
    """Deletes a club definition."""
    db_club = get_club_by_id(db, club_id)
    if not db_club: return False

    # IMPORTANT: Dependency Check
    # If you add student memberships (e.g., StudentClub table), check here first!
    # member_exists = db.query(models.StudentClub.id).filter(models.StudentClub.club_id == club_id).first()
    # if member_exists:
    #     raise ValueError(f"Cannot delete club '{db_club.name}' as students are still members.")

    try:
        db.delete(db_club); db.commit()
        logger.info(f"Deleted club {club_id} ('{db_club.name}')")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error deleting club {club_id}: {e}");
        raise ValueError("Database error deleting club.")

def get_clubs_joined_by_student(db: Session, student_id: int) -> List[models.StudentClub]:
    """Gets the StudentClub membership records for a student, loading club details."""
    logger.debug(f"Fetching clubs joined by student {student_id}")
    return db.query(models.StudentClub).options(
        joinedload(models.StudentClub.club) # Eager load club info
    ).filter(models.StudentClub.student_id == student_id).order_by(models.StudentClub.join_date.desc()).all()

def get_clubs_not_joined_by_student(db: Session, student_id: int) -> List[models.Club]:
    """Gets clubs that a student is NOT currently a member of."""
    logger.debug(f"Fetching clubs NOT joined by student {student_id}")
    # Subquery for club IDs the student HAS joined
    joined_club_ids = db.query(models.StudentClub.club_id).filter(
        models.StudentClub.student_id == student_id
    ).subquery()

    # Query clubs whose IDs are NOT in the subquery
    available_clubs = db.query(models.Club).filter(
        models.Club.id.notin_(joined_club_ids)
    ).order_by(models.Club.name).all()
    # TODO: Add filtering for active clubs if 'is_active' flag is added
    return available_clubs

def student_join_club(db: Session, student_id: int, club_id: int) -> models.StudentClub:
    """Creates a membership record for a student joining a club."""
    # 1. Check student and club exist
    if not db.query(models.Student.id).filter(models.Student.id == student_id).first():
        raise ValueError("Student not found.")
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    if not club:
        raise ValueError("Club not found.")
    # TODO: Check if club is active if 'is_active' flag exists

    # 2. Check if already a member (using the unique constraint is better)
    # existing = db.query(models.StudentClub.id).filter_by(student_id=student_id, club_id=club_id).first()
    # if existing: raise ValueError("Already a member of this club.")

    # 3. Create membership record
    db_membership = models.StudentClub(student_id=student_id, club_id=club_id)
    db.add(db_membership)
    try:
        db.commit()
        db.refresh(db_membership)
        logger.info(f"Student {student_id} joined club {club_id} ('{club.name}')")
        return db_membership
    except IntegrityError as e: # Catch unique constraint violation
        db.rollback()
        logger.warning(f"Student {student_id} attempted to join club {club_id} again: {e}")
        raise ValueError("Already a member of this club.")
    except Exception as e:
        db.rollback(); logger.error(f"Error joining club: {e}")
        raise ValueError("Database error processing club join request.")


def student_leave_club(db: Session, student_id: int, club_id: int) -> bool:
    """Deletes a membership record for a student leaving a club."""
    # Find the specific membership record to delete
    db_membership = db.query(models.StudentClub).filter(
        models.StudentClub.student_id == student_id,
        models.StudentClub.club_id == club_id
    ).first()

    if not db_membership:
        logger.warning(f"Student {student_id} attempted to leave club {club_id} they are not a member of.")
        return False # Or raise ValueError("Not a member of this club.")

    try:
        db.delete(db_membership)
        db.commit()
        logger.info(f"Student {student_id} left club {club_id}")
        return True
    except Exception as e:
        db.rollback(); logger.error(f"Error leaving club: {e}");
        raise ValueError("Database error processing leave club request.")