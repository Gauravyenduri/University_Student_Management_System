# app/services/fee_service.py
from sqlalchemy.orm import Session, joinedload, selectinload
from app import models
from typing import List, Optional, Dict, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func # Import func for ilike
from typing import Optional, List
from app import models

# ... other imports and functions ...

def get_all_fee_payments(
    db: Session,
    student_id: Optional[int] = None,
    status: Optional[str] = None,
    search_student: Optional[str] = None 
) -> List[models.FeePayment]:
    """
    Retrieves all fee payments, optionally filtering by student ID, status,
    and searching by student name.
    """
    # Start base query with eager loading
    query = db.query(models.FeePayment).options(
        joinedload(models.FeePayment.student).joinedload(models.Student.user) # Load student -> user
    ).join(models.FeePayment.student) # Ensure Student is joined for filtering/ordering

    if student_id:
        query = query.filter(models.FeePayment.student_id == student_id)

    if status and status in models.PaymentStatus.__members__: # Filter by valid status enum name
         query = query.filter(models.FeePayment.status == models.PaymentStatus[status])

    if search_student:
        # Use ilike for case-insensitive partial matching
        search_term = f"%{search_student}%"
        query = query.filter(models.Student.name.ilike(search_term))
    query = query.order_by(models.FeePayment.date.desc(), models.Student.name)

    return query.all()

def get_fee_payment_by_id(db: Session, payment_id: int) -> Optional[models.FeePayment]:
     return db.query(models.FeePayment).options(
         joinedload(models.FeePayment.student).joinedload(models.Student.user)
     ).filter(models.FeePayment.id == payment_id).first()

def create_fee_record(db: Session, student_id: int, amount: float, due_date: date, description: Optional[str] = "Fee Due") -> models.FeePayment:
    # Check if student exists
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student with ID {student_id} not found.")

    # You might add checks here to prevent duplicate fee records for the same period/type

    db_fee = models.FeePayment(
        student_id=student_id,
        amount=amount,
        # description=description, # Add description field to FeePayment model if needed
        date=due_date, # Use 'date' field likely as the 'due date' initially? Clarify model usage.
        status=models.PaymentStatus.PENDING # Default status
        # payment_method=None, # Null initially
    )
    db.add(db_fee)
    try:
        db.commit(); db.refresh(db_fee)
        return db_fee
    except Exception as e:
        db.rollback(); logger.error(f"Error creating fee record: {e}");
        raise ValueError("Database error creating fee record.")
def update_fee_record_details(db: Session, payment_id: int, update_data: Dict[str, Any]) -> Optional[models.FeePayment]:
    """Updates details of a fee record (description, due date, amount due) - Admin action."""
    # Does NOT update payment status/details directly
    db_fee = get_fee_payment_by_id(db, payment_id)
    if not db_fee: return None

    updated = False
    # Only allow edits if not already fully PAID? Or allow correcting details? Let's allow for now.
    # if db_fee.status == models.PaymentStatus.PAID:
    #     raise ValueError("Cannot edit details of an already paid fee record.")

    if 'description' in update_data:
        new_desc = update_data['description']
        if db_fee.description != new_desc: db_fee.description = new_desc; updated = True
    if 'amount' in update_data: # Amount DUE
        new_amount = update_data['amount'] # Expected float
        if new_amount is None or new_amount <= 0: raise ValueError("Amount due must be positive.")
        if db_fee.amount != new_amount:
             db_fee.amount = new_amount; updated = True
             # If amount due changed, maybe reset payment status if partially paid? Or recalculate below?
    if 'date' in update_data: # Due Date
        new_date = update_data['date'] # Expected date object
        if db_fee.date != new_date: db_fee.date = new_date; updated = True
    if 'status' in update_data and update_data['status'] == models.PaymentStatus.CANCELLED.name: # Allow admin to cancel
        if db_fee.status != models.PaymentStatus.CANCELLED:
             db_fee.status = models.PaymentStatus.CANCELLED
             db_fee.amount_paid = 0.0 # Reset paid amount on cancel? Optional.
             db_fee.payment_date = None
             updated = True
    # Admin should NOT set PAID/PARTIALLY_PAID status directly here.

    # Recalculate OVERDUE status based on potentially new due date if PENDING/PARTIALLY
    if db_fee.status in [models.PaymentStatus.PENDING]:
        if db_fee.date < date.today():
            if db_fee.status != models.PaymentStatus.OVERDUE:
                db_fee.status = models.PaymentStatus.OVERDUE
                updated = True
        else: # Not overdue anymore
             if db_fee.status == models.PaymentStatus.OVERDUE:
                 # Revert to PENDING or PARTIALLY_PAID based on amount_paid
                 new_pending_status = models.PaymentStatus.PENDING
                 db_fee.status = new_pending_status
                 updated = True

    if not updated: return db_fee # No changes made

    try:
        db.add(db_fee); db.commit(); db.refresh(db_fee)
        logger.info(f"Admin updated fee record {payment_id} details.")
        return db_fee
    except Exception as e:
        db.rollback(); logger.error(f"Error updating fee record details {payment_id}: {e}");
        raise ValueError("Database error updating fee record details.")

# --- NEW: Service for Student Payment Action ---
def record_student_payment(db: Session, payment_id: int, student_id: int) -> Optional[models.FeePayment]:
    """Marks a fee record as PAID by the student."""
    db_fee = db.query(models.FeePayment).filter(
        models.FeePayment.id == payment_id,
        models.FeePayment.student_id == student_id # Ensure student owns the record
    ).first()

    if not db_fee:
        logger.warning(f"Student {student_id} tried to pay non-existent/unauthorized fee record {payment_id}")
        return None # Not found or doesn't belong to student

    # Check if already paid or cancelled
    if db_fee.status in [models.PaymentStatus.PAID]:
        raise ValueError(f"Fee record is already {db_fee.status.value.lower()} and cannot be paid again.")

    # Mark as fully paid (simple model)
    db_fee.amount_paid = db_fee.amount # Set paid amount to full amount due
    db_fee.payment_date = date.today() # Set payment date to today
    db_fee.status = models.PaymentStatus.PAID
    db_fee.payment_method = "Student Portal" # Indicate payment source

    try:
        db.add(db_fee)
        db.commit()
        db.refresh(db_fee)
        logger.info(f"Student {student_id} marked fee record {payment_id} as PAID.")
        return db_fee
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording student payment for fee {payment_id}: {e}", exc_info=True)
        raise ValueError("Database error recording payment.")

def update_fee_payment(db: Session, payment_id: int, update_data: Dict[str, Any]) -> Optional[models.FeePayment]:
    """Updates an existing fee payment record, recalculating status."""
    print(f"Updating fee payment {payment_id} with data: {update_data}")
    db_fee = get_fee_payment_by_id(db, payment_id)
    if not db_fee:
        return None # Not found

    updated = False # Track if any actual change occurred

    # --- Update Editable Fields ---
    # Check and update amount_paid
    if 'amount_paid' in update_data:
        paid = update_data['amount_paid'] # Expected float or None
        if paid is None: paid = 0.0
        if paid < 0: raise ValueError("Paid amount cannot be negative.")
        # Allow overpayment? Or cap at amount due? Let's cap for now.
        # If you want to allow overpayment, remove this check.
        # if paid > db_fee.amount: raise ValueError(f"Paid amount ({paid:.2f}) cannot exceed amount due ({db_fee.amount:.2f}).")
        if db_fee.amount_paid != paid:
            db_fee.amount_paid = paid
            updated = True

    # Check and update payment_method
    if 'payment_method' in update_data:
        # Allow setting to None or empty string which becomes None?
        new_method = update_data['payment_method']
        if new_method is not None: new_method = new_method.strip() if new_method else None # Handle empty string
        if db_fee.payment_method != new_method:
            db_fee.payment_method = new_method
            updated = True

    # Check and update description (if you allow editing it)
    # if 'description' in update_data:
    #    new_desc = update_data['description']
    #    if db_fee.description != new_desc: db_fee.description = new_desc; updated = True

    # Check and update amount (due) (if you allow editing it)
    # if 'amount' in update_data: ... update db_fee.amount; updated = True ...

    # Check and update date (due date) (if you allow editing it)
    # if 'date' in update_data: ... update db_fee.date; updated = True ...


    # --- Determine New Status ---
    # Allow manual override ONLY for CANCELLED status? Or any?
    # Let's prioritize calculation based on payment, unless CANCELLED is chosen.
    manual_status_update = False
    new_status_enum = db_fee.status # Start with current status

    if 'status' in update_data:
        new_status_str = update_data['status']
        if new_status_str:
            new_status_enum = models.PaymentStatus[new_status_str.upper()]
            manual_status_update = True # A specific status was requested
            if db_fee.status != new_status_enum:
                updated = True # Status change counts as update
        elif new_status_str: # Invalid status provided
            raise ValueError(f"Invalid status value provided: {new_status_str}")

    # If status wasn't manually set OR it was manually set but NOT to CANCELLED,
    # recalculate based on payment details.
    if not manual_status_update:
        calculated_status = models.PaymentStatus.PENDING # Default if no other condition met
        current_date = date.today()

        # Use the potentially updated amount_paid from earlier
        current_amount_paid = db_fee.amount_paid

        if current_amount_paid >= db_fee.amount:
            calculated_status = models.PaymentStatus.PAID
        elif current_amount_paid > 0:
            calculated_status = models.PaymentStatus.PENDING
        # Only check overdue if not paid at all or partially paid
        if calculated_status != models.PaymentStatus.PAID and db_fee.date < current_date:
             # If overdue, OVERDUE overrides PENDING or PARTIALLY_PAID visually/logically?
             # Let's say Overdue is a state independent of payment progress for now
             # Maybe add a separate "is_overdue" flag/property?
             # For now, let's keep it simple: If past due & not fully paid -> OVERDUE
             # This means partially paid but late shows as OVERDUE. Adjust if needed.
             calculated_status = models.PaymentStatus.OVERDUE

        # Only update if calculated status differs from current/manually set status
        if db_fee.status != calculated_status:
            db_fee.status = calculated_status
            updated = True


    # If no fields actually changed, don't hit the DB
    if not updated:
        logger.debug(f"No actual changes detected for fee payment {payment_id}. Skipping update.")
        return db_fee

    # --- Commit Changes ---
    try:
        print(f"Updating fee payment {payment_id} with data: {update_data}")
        db.add(db_fee)
        db.commit()
        db.refresh(db_fee)
        logger.info(f"Successfully updated fee payment {payment_id}. New status: {db_fee.status.value}")
        return db_fee
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing fee payment update {payment_id}: {e}", exc_info=True)
        raise ValueError("Database error during fee payment update.")

def delete_fee_record(db: Session, payment_id: int) -> bool:
     db_fee = get_fee_payment_by_id(db, payment_id)
     if not db_fee: return False
     # Add checks if needed (e.g., cannot delete if partially/fully paid?)
     try:
         db.delete(db_fee); db.commit()
         return True
     except Exception as e:
         db.rollback(); logger.error(f"Error deleting fee record {payment_id}: {e}");
         raise ValueError("Database error deleting fee record.")