# app/services/scholarship_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import models
from typing import List, Optional, Dict, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

# --- Scholarship Definition CRUD ---
def get_all_scholarship_definitions(db: Session) -> List[models.Scholarship]:
    return db.query(models.Scholarship).order_by(models.Scholarship.name).all()

def get_scholarship_definition_by_id(db: Session, scholarship_id: int) -> Optional[models.Scholarship]:
    return db.query(models.Scholarship).filter(models.Scholarship.id == scholarship_id).first()

def create_scholarship_definition(db: Session, name: str, amount: float, eligibility: Optional[str]) -> models.Scholarship:
    if db.query(models.Scholarship).filter(func.lower(models.Scholarship.name) == func.lower(name)).first():
        raise ValueError(f"Scholarship named '{name}' already exists.")
    db_schol = models.Scholarship(name=name, amount=amount, eligibility=eligibility)
    db.add(db_schol)
    try: db.commit(); db.refresh(db_schol); return db_schol
    except Exception as e: db.rollback(); logger.error(f"Error creating scholarship def: {e}"); raise ValueError("DB error.")

def update_scholarship_definition(db: Session, scholarship_id: int, update_data: Dict[str, Any]) -> Optional[models.Scholarship]:
    db_schol = get_scholarship_definition_by_id(db, scholarship_id)
    if not db_schol: return None
    new_name = update_data.get('name')
    if new_name and func.lower(new_name) != func.lower(db_schol.name):
         db_schol.name = new_name
    if 'amount' in update_data: db_schol.amount = update_data['amount'] # Add validation?
    if 'eligibility' in update_data: db_schol.eligibility = update_data['eligibility']
    try: db.add(db_schol); db.commit(); db.refresh(db_schol); return db_schol
    except Exception as e: db.rollback(); logger.error(f"Error updating scholarship def {scholarship_id}: {e}"); raise ValueError("DB error.")

def delete_scholarship_definition(db: Session, scholarship_id: int) -> bool:
    db_schol = get_scholarship_definition_by_id(db, scholarship_id)
    if not db_schol: return False
    # Check if assigned before deleting
    assignment_exists = db.query(models.StudentScholarship.id).filter(models.StudentScholarship.scholarship_id == scholarship_id).first()
    if assignment_exists:
        raise ValueError(f"Cannot delete scholarship '{db_schol.name}' as it is assigned to students.")
    try: db.delete(db_schol); db.commit(); return True
    except Exception as e: db.rollback(); logger.error(f"Error deleting scholarship def {scholarship_id}: {e}"); raise ValueError("DB error.")

# --- Scholarship Assignment CRUD ---
def get_all_scholarship_assignments(db: Session) -> List[models.StudentScholarship]:
     return db.query(models.StudentScholarship).options(
         joinedload(models.StudentScholarship.student).joinedload(models.Student.user),
         joinedload(models.StudentScholarship.scholarship)
     ).order_by(models.StudentScholarship.award_date.desc()).all()

def assign_scholarship_to_student(db: Session, student_id: int, scholarship_id: int, academic_year: Optional[str]) -> models.StudentScholarship:
     # Check student/scholarship exist
     if not db.query(models.Student).filter(models.Student.id == student_id).first(): raise ValueError("Student not found.")
     if not db.query(models.Scholarship).filter(models.Scholarship.id == scholarship_id).first(): raise ValueError("Scholarship not found.")
     # Check if already assigned (optional: depends on unique constraint)
     # existing = db.query(models.StudentScholarship).filter_by(student_id=student_id, scholarship_id=scholarship_id, academic_year=academic_year).first()
     # if existing: raise ValueError("Scholarship already assigned to this student for this year.")

     db_assign = models.StudentScholarship(student_id=student_id, scholarship_id=scholarship_id, academic_year=academic_year)
     db.add(db_assign)
     try: db.commit(); db.refresh(db_assign); return db_assign
     except Exception as e: db.rollback(); logger.error(f"Error assigning scholarship: {e}"); raise ValueError("DB error.")

def revoke_scholarship_assignment(db: Session, assignment_id: int) -> bool:
    db_assign = db.query(models.StudentScholarship).filter(models.StudentScholarship.id == assignment_id).first()
    if not db_assign: return False
    try: db.delete(db_assign); db.commit(); return True
    except Exception as e: db.rollback(); logger.error(f"Error revoking scholarship assignment {assignment_id}: {e}"); raise ValueError("DB error.")

# Helper for update_scholarship_definition check
def get_scholarship_definition_by_name(db: Session, name: str) -> Optional[models.Scholarship]:
    return db.query(models.Scholarship).filter(func.lower(models.Scholarship.name) == func.lower(name)).first()