# University-Management-System
The Student Management System enhances academic operations by managing student data, course details, faculty records, and assessments. It improves efficiency, ensures data stability, and supports better decision-making in educational institutions.
Student Management System
A full-stack Student Management System built with FastAPI, SQLAlchemy, PostgreSQL, Jinja2, and HTML/CSS.
This project aims to simplify and automate various operations for educational institutions — including student enrollment, course management, scheduling, fee payment, library management, and more.

# Features
Authentication & Authorization

Secure login for Admin, Student, and Instructor roles

Role-based access control

JWT-based session management

Admin Panel

Manage Students, Instructors, Courses, Classrooms, Departments

Handle Fee structures, Scholarships, Hostel allocations, Library operations

Club creation, Complaint management, Alumni connections

Student Portal

View schedules, attendance, grades

Manage course enrollments

Access fee payment status and scholarship details

Instructor Portal

Manage student discipline

Assign grades and monitor academic progress

View class schedules

Database Integration

SQLAlchemy ORM

PostgreSQL database

Auto migration of tables on startup

Security

Password hashing with strong encryption

Secure admin creation during app startup

CORS and input validation

Frontend (Templates)

Jinja2 templating engine

Modular static files (HTML, CSS, JavaScript)

# Tech Stack
Backend: FastAPI, Python

Frontend: Jinja2, HTML, CSS

Database: PostgreSQL, SQLAlchemy ORM

Authentication: JWT tokens, OAuth2

Deployment/Server: Uvicorn ASGI server

Environment Management: Python-dotenv

# Setup Instructions
Clone the repository


git clone https://github.com/your-username/student-management-system.git
cd student-management-system
Create and activate a virtual environment

python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
Install dependencies


pip install -r requirements.txt
Setup environment variables
Create a .env file in the root directory:


DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=admin123
DATABASE_URL=postgresql://yourusername:yourpassword@localhost/yourdatabase
Run the application


uvicorn app.main:app --reload
Access the app
Open your browser and visit:
http://127.0.0.1:8000

# Project Structure
app/

├── main.py             # Main FastAPI application

├── database.py         # Database session and engine

├── models.py           # SQLAlchemy models (User, Roles, etc.)

├── services/           # Authentication and business logic

├── routes/             # All route modules (auth, admin, student, etc.)

├── templates/          # Jinja2 HTML templates

├── static/             # CSS, JS, images

├── .env                # Environment variables (local)

├── requirements.txt    # Project dependencies
