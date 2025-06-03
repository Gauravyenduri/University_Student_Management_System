import enum
import datetime
from datetime import date
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, Date, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship # Use declarative_base from orm
from passlib.context import CryptContext # Import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

Base = declarative_base()

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False) # Added index=True
    email = Column(String(100), unique=True, index=True, nullable=False) # Added index=True
    # Rename 'password' to 'hashed_password' for clarity
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Corrected Password Handling Methods
    def set_password(self, plain_password):
        """Hashes the plain password and stores it."""
        self.hashed_password = pwd_context.hash(plain_password)

    def verify_password(self, plain_password):
        """Verifies a plain password against the stored hash."""
        return pwd_context.verify(plain_password, self.hashed_password)

    # Relationships (Linking Student/Instructor back to User)
    # Add these if a User is created *first* and then linked to a Student/Instructor profile
    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    instructor_profile = relationship("Instructor", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Student(Base):
    __tablename__ = "students"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False) # Assuming every student MUST be a user
    name = Column(String(100), nullable=False)
    dob = Column(Date, nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True) # Link student to a department

    # Relationships
    user = relationship("User", back_populates="student_profile")
    department = relationship("Department", back_populates="students") # Relationship to Department
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    scholarship_assignments = relationship("StudentScholarship", back_populates="student", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="student", cascade="all, delete-orphan")
    attendance_records = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    library_records = relationship("Library", back_populates="student", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="student", cascade="all, delete-orphan")
    fee_payments = relationship("FeePayment", back_populates="student", cascade="all, delete-orphan")
    hostel_records = relationship("Hostel", back_populates="student", cascade="all, delete-orphan")
    discipline_records = relationship("DisciplineRecord", back_populates="student", cascade="all, delete-orphan")
    guardians = relationship("Guardian", back_populates="student", cascade="all, delete-orphan")
    complaints = relationship("Complaint", back_populates="student", cascade="all, delete-orphan")
    alumni_record = relationship("Alumni", back_populates="student", uselist=False)
    club_memberships = relationship("StudentClub", back_populates="student", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    head_of_department_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    instructors = relationship(
        "Instructor",
        back_populates="department",
        foreign_keys="Instructor.department_id", # Explicitly state FK if needed
        cascade="all, delete-orphan" # Or adjust cascade as needed
    )
    hod_instructor = relationship(
        "Instructor",
        # Specify the foreign key column for this specific relationship
        primaryjoin="Department.head_of_department_id == Instructor.id",
        # Prevent back-population issues if an instructor can only head one dept
        backref="headed_department",
        uselist=False # A department has only one HoD
    )
    students = relationship("Student", back_populates="department", cascade="all, delete-orphan") # Students in this department
    courses = relationship("Course", back_populates="department", cascade="all, delete-orphan") # Courses offered by this department

class Instructor(Base):
    __tablename__ = "instructors"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False) # Assuming every instructor MUST be a user
    name = Column(String(100), nullable=False)
    qualification = Column(String(100), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="instructor_profile")
    department = relationship(
        "Department",
        back_populates="instructors",
        foreign_keys=[department_id] # Specify FK
    )
    schedules = relationship("Schedule", back_populates="instructor", cascade="all, delete-orphan")

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    credits = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False) # Link course to a department
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    department = relationship("Department", back_populates="courses") # Relationship to Department
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="course", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="course", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="course", cascade="all, delete-orphan")

class Enrollment(Base):
    __tablename__ = "enrollments"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    enrollment_date = Column(Date, default=datetime.date.today)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

class Classroom(Base):
    __tablename__ = "classrooms"
    
    id = Column(Integer, primary_key=True, index=True)
    location = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    schedules = relationship("Schedule", back_populates="classroom", cascade="all, delete-orphan")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    instructor_id = Column(Integer, ForeignKey("instructors.id"))
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)
    day_of_week = Column(String(20), nullable=True)
    start_time = Column(String(20), nullable=True)
    end_time = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    course = relationship("Course", back_populates="schedules")
    instructor = relationship("Instructor", back_populates="schedules")
    classroom = relationship("Classroom", back_populates="schedules")
    attendance_records = relationship("Attendance", back_populates="schedule", cascade="all, delete-orphan") # Attendance for this specific schedule

class Grade(Base):
    __tablename__ = "grades"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    marks = Column(Float, nullable=True)
    grade = Column(String(5), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="grades")
    course = relationship("Course", back_populates="grades")

class AttendanceStatus(enum.Enum):
    PRESENT = "Present"
    ABSENT = "Absent"
    LATE = "Late"
    EXCUSED = "Excused"

class Attendance(Base):
    __tablename__ = "attendance"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False) # Link to specific schedule/session
    date = Column(Date, default=datetime.date.today)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    # Relationships
    student = relationship("Student", back_populates="attendance_records")
    schedule = relationship("Schedule", back_populates="attendance_records") # Link back to Schedule

class Library(Base):
    __tablename__ = "library_records"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    books_borrowed = Column(Integer, default=0)
    borrowed_date = Column(Date, nullable=True)
    return_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="library_records")

class ExamType(str, enum.Enum): # Keep this as is
    MIDTERM = "Midterm"
    FINAL = "Final"
    QUIZ = "Quiz"
    ASSIGNMENT = "Assignment" 
    PROJECT = "Project" 

class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name = Column(String(150), nullable=False) # e.g., "Midterm 1 - MCQs"
    date = Column(Date, nullable=True)
    type = Column(Enum(ExamType), nullable=False, default=ExamType.QUIZ)
    total_marks = Column(Float, nullable=True, default=0.0)
    description = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    course = relationship("Course", back_populates="exams")
    results = relationship("Result", back_populates="exam", cascade="all, delete-orphan")
    mcq_questions = relationship("MCQQuestion", back_populates="exam", cascade="all, delete-orphan", lazy="selectin")

# === MCQ Question Model ===
class MCQQuestion(Base):
    __tablename__ = "mcq_questions"
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    marks = Column(Float, nullable=False, default=1.0) # Marks for this specific question

    # Options (Store as JSON or separate table? JSON simpler for now)
    # Option Format: [{"text": "Option A", "is_correct": false}, {"text": "Option B", "is_correct": true}, ...]
    options = Column(Text, nullable=False) # Store JSON string of options

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship back to Exam
    exam = relationship("Exam", back_populates="mcq_questions")

class Result(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    score = Column(Float, nullable=True) # Final calculated score
    grade = Column(String(5), nullable=True)
    # ADDED: Track submission time and status
    submitted_at = Column(DateTime, nullable=True) # When the student submitted
    is_graded = Column(Boolean, default=False) # Has the instructor graded/finalized?

    created_at = Column(DateTime, default=func.now()) # When the attempt *started* or record created
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="results")
    exam = relationship("Exam", back_populates="results")
    # === NEW RELATIONSHIP ===
    mcq_answers = relationship("MCQAnswer", back_populates="result", cascade="all, delete-orphan")

class MCQAnswer(Base):
   __tablename__ = "mcq_answers"
   id = Column(Integer, primary_key=True, index=True)
   result_id = Column(Integer, ForeignKey("results.id"), nullable=False) # Link to the overall Result/Attempt
   mcq_question_id = Column(Integer, ForeignKey("mcq_questions.id"), nullable=False)
   # Store the *index* or *text* of the chosen option? Index is less storage, Text is more explicit. Let's use index.
   # Need to ensure option order is consistent when displaying and grading.
   # Store the actual option text selected might be safer if option order can change? Let's store text for safety.
   selected_option_text = Column(Text, nullable=True) # Text of the chosen option
   is_correct = Column(Boolean, nullable=True) # Was this answer correct when graded?

   # Relationship back to the overall result/attempt
   result = relationship("Result", back_populates="mcq_answers")

class PaymentStatus(enum.Enum):
    PENDING = "Pending"
    PAID = "Paid"
    CANCELLED = "Cancelled"
    OVERDUE = "Overdue"
    REFUNDED = "Refunded"

class FeePayment(Base):
    __tablename__ = "fee_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String(255), nullable=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0, nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    payment_method = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="fee_payments")
    @property
    def balance(self) -> float:
        # Ensure values are treated as floats, default to 0 if None (though nullable=False should prevent None)
        due = self.amount if self.amount is not None else 0.0
        paid = self.amount_paid if self.amount_paid is not None else 0.0
        return round(due - paid, 2) # Round to 2 decimal places

class Scholarship(Base):
    __tablename__ = "scholarships"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    eligibility = Column(Text, nullable=True)
    amount = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    student_assignments = relationship("StudentScholarship", back_populates="scholarship", cascade="all, delete-orphan")

class StudentScholarship(Base):
    __tablename__ = "student_scholarships"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    scholarship_id = Column(Integer, ForeignKey("scholarships.id"), nullable=False)
    award_date = Column(Date, default=datetime.date.today)
    academic_year = Column(String(20), nullable=True) # e.g., "2023-2024"
    created_at = Column(DateTime, default=func.now())

    student = relationship("Student", back_populates="scholarship_assignments")
    scholarship = relationship("Scholarship", back_populates="student_assignments")

class Hostel(Base):
    __tablename__ = "hostels"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    hostel_name = Column(String(100), nullable=False) # e.g., "Block A", "North Hostel"
    room_number = Column(String(20), nullable=True)
    fees = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="hostel_records")

class DisciplineRecord(Base):
    __tablename__ = "discipline_records"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    incident_description = Column(Text, nullable=False) # Make incident required
    action_taken = Column(Text, nullable=True) # Action might be decided later
    incident_date = Column(Date, default=date.today, nullable=False) # Date of incident required

    created_at = Column(DateTime, default=func.now()) # Record creation time
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now()) # Record update time

    # Relationship back to the student
    student = relationship("Student", back_populates="discipline_records")

class Guardian(Base):
    __tablename__ = "guardians"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    name = Column(String(100), nullable=False)
    relationship_type = Column(String(50), nullable=True)  # Changed from 'relationship' to avoid conflict
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="guardians")

class Club(Base):
    __tablename__ = "clubs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    members = relationship("StudentClub", back_populates="club", cascade="all, delete-orphan")


class StudentClub(Base):
    __tablename__ = "student_clubs" # Table to link students and clubs

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    join_date = Column(Date, default=date.today, nullable=False)
    # Optional: Add role within the club? (e.g., 'Member', 'President')
    # role = Column(String(50), default='Member')

    created_at = Column(DateTime, default=func.now())

    # Relationships back to Student and Club
    student = relationship("Student", back_populates="club_memberships")
    club = relationship("Club", back_populates="members")

    # Ensure a student can only join a specific club once
    __table_args__ = (UniqueConstraint('student_id', 'club_id', name='_student_club_membership_uc'),)

class ComplaintStatus(enum.Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"

class Complaint(Base):
    __tablename__ = "complaints"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    description = Column(Text, nullable=False)
    status = Column(Enum(ComplaintStatus), nullable=False, default=ComplaintStatus.OPEN)
    date = Column(Date, default=datetime.date.today)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="complaints")

class Alumni(Base):
    __tablename__ = "alumni"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), unique=True)
    graduation_year = Column(Integer, nullable=True)
    current_job = Column(String(100), nullable=True)
    current_employer = Column(String(100), nullable=True)
    contact_info = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="alumni_record")
