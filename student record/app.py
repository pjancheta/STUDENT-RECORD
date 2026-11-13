import csv
import io
import os
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import click
from dotenv import load_dotenv
from flask import Flask, Response, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import (
    DateField,
    PasswordField,
    SelectChoice,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "info"

COURSES = [
    "Accountancy",
    "Business Administration",
    "Computer Science",
    "Education",
    "Engineering",
    "Information Technology",
    "Nursing",
    "Other",
]


def normalize_database_url(database_url):
    if database_url and database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url and database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Admin(UserMixin, db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False, index=True)
    middle_name = db.Column(db.String(80))
    gender = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    contact_number = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    course = db.Column(db.String(100), nullable=False, index=True)
    year_level = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    @property
    def full_name(self):
        return " ".join(
            name for name in (self.first_name, self.middle_name, self.last_name) if name
        )


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class StudentForm(FlaskForm):
    student_id = StringField(
        "Student ID",
        validators=[
            DataRequired(),
            Length(max=32),
            Regexp(r"^[A-Za-z0-9._-]+$", message="Use letters, numbers, dots, _ or - only."),
        ],
    )
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    middle_name = StringField("Middle name", validators=[Optional(), Length(max=80)])
    gender = SelectField(
        "Gender",
        choices=[
            SelectChoice("", "Select gender"),
            SelectChoice("Female", "Female"),
            SelectChoice("Male", "Male"),
            SelectChoice("Other", "Other"),
        ],
        validators=[DataRequired()],
    )
    date_of_birth = DateField("Date of birth", validators=[DataRequired()])
    email = StringField("Email address", validators=[DataRequired(), Email(), Length(max=254)])
    contact_number = StringField(
        "Contact number",
        validators=[
            DataRequired(),
            Length(max=30),
            Regexp(r"^[0-9+().\-\s]+$", message="Enter a valid phone number."),
        ],
    )
    address = TextAreaField("Address", validators=[DataRequired(), Length(max=300)])
    course = SelectField(
        "Course / program",
        choices=[SelectChoice("", "Select a course")]
        + [SelectChoice(course, course) for course in COURSES],
        validators=[DataRequired()],
    )
    year_level = SelectField(
        "Year level",
        choices=[SelectChoice("", "Select year")]
        + [SelectChoice(str(year), f"Year {year}") for year in range(1, 7)],
        validators=[DataRequired()],
        coerce=str,
    )
    submit = SubmitField("Save student")

    def validate_date_of_birth(self, field):
        if field.data and field.data >= date.today():
            raise ValidationError("Date of birth must be in the past.")


class SettingsForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[
            DataRequired(),
            Length(min=12, max=128, message="Use at least 12 characters."),
            Regexp(
                r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).+$",
                message="Include uppercase, lowercase, a number, and a symbol.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")],
    )
    submit = SubmitField("Update password")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=normalize_database_url(os.environ.get("DATABASE_URL"))
        or "sqlite:///students.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true",
        SESSION_COOKIE_SAMESITE="Lax",
        WTF_CSRF_TIME_LIMIT=3600,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "test-only-secret"
        else:
            raise RuntimeError("SECRET_KEY must be configured in the environment.")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(Admin, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    @app.context_processor
    def inject_template_values():
        return {"today": date.today().isoformat()}

    @app.cli.command("init-db")
    def init_db_command():
        """Create tables and create the initial admin when configured."""
        db.create_all()
        _ensure_initial_admin()
        click.echo("Database tables are ready.")

    @app.cli.command("seed-admin")
    def seed_admin_command():
        """Create the initial admin in an already-migrated database."""
        _ensure_initial_admin()
        click.echo("Initial administrator is ready.")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        form = LoginForm()
        if form.validate_on_submit():
            admin = db.session.scalar(select(Admin).where(Admin.username == form.username.data.strip()))
            if admin and admin.check_password(form.password.data):
                login_user(admin, remember=False, fresh=True)
                next_url = request.args.get("next", "")
                parsed_next = urlparse(next_url)
                if next_url and not parsed_next.netloc and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))
            flash("The username or password is incorrect.", "error")
        return render_template("login.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        total = db.session.scalar(select(db.func.count(Student.id))) or 0
        male = db.session.scalar(
            select(db.func.count(Student.id)).where(Student.gender == "Male")
        ) or 0
        female = db.session.scalar(
            select(db.func.count(Student.id)).where(Student.gender == "Female")
        ) or 0
        recent = db.session.scalars(
            select(Student).order_by(Student.created_at.desc(), Student.id.desc()).limit(5)
        ).all()
        course_stats = db.session.execute(
            select(Student.course, db.func.count(Student.id))
            .group_by(Student.course)
            .order_by(db.func.count(Student.id).desc(), Student.course.asc())
            .limit(6)
        ).all()
        return render_template(
            "dashboard.html",
            total=total,
            male=male,
            female=female,
            recent=recent,
            course_stats=course_stats,
        )

    @app.route("/students")
    @login_required
    def students():
        search = request.args.get("q", "").strip()[:100]
        gender = request.args.get("gender", "").strip()
        course = request.args.get("course", "").strip()
        year_level = request.args.get("year", "").strip()
        query = select(Student)
        if search:
            term = f"%{search}%"
            query = query.where(
                or_(
                    Student.student_id.ilike(term),
                    Student.first_name.ilike(term),
                    Student.middle_name.ilike(term),
                    Student.last_name.ilike(term),
                    (Student.first_name + " " + Student.last_name).ilike(term),
                )
            )
        if gender in {"Female", "Male", "Other"}:
            query = query.where(Student.gender == gender)
        if course in COURSES:
            query = query.where(Student.course == course)
        if year_level.isdigit() and 1 <= int(year_level) <= 6:
            query = query.where(Student.year_level == int(year_level))
        page = request.args.get("page", 1, type=int)
        pagination = db.paginate(
            query.order_by(Student.created_at.desc(), Student.id.desc()),
            page=max(page, 1),
            per_page=10,
            error_out=False,
        )
        return render_template(
            "students.html",
            pagination=pagination,
            courses=COURSES,
            filters={"q": search, "gender": gender, "course": course, "year": year_level},
        )

    @app.route("/students/new", methods=["GET", "POST"])
    @login_required
    def add_student():
        form = StudentForm()
        if form.validate_on_submit():
            student = Student()
            _populate_student(student, form)
            db.session.add(student)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That student ID or email address is already in use.", "error")
            else:
                flash("Student record added.", "success")
                return redirect(url_for("students"))
        return render_template("student_form.html", form=form, title="Add new student")

    @app.route("/students/<int:student_pk>/edit", methods=["GET", "POST"])
    @login_required
    def edit_student(student_pk):
        student = db.get_or_404(Student, student_pk)
        form = StudentForm(obj=student)
        if request.method == "GET":
            form.year_level.data = str(student.year_level)
        if form.validate_on_submit():
            _populate_student(student, form)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That student ID or email address is already in use.", "error")
            else:
                flash("Student record updated.", "success")
                return redirect(url_for("students"))
        return render_template("student_form.html", form=form, title="Edit student", student=student)

    @app.post("/students/<int:student_pk>/delete")
    @login_required
    def delete_student(student_pk):
        student = db.get_or_404(Student, student_pk)
        db.session.delete(student)
        db.session.commit()
        flash(f"{student.full_name}'s record was deleted.", "success")
        return redirect(url_for("students"))

    @app.route("/reports")
    @login_required
    def reports():
        course_stats = db.session.execute(
            select(Student.course, db.func.count(Student.id))
            .group_by(Student.course)
            .order_by(db.func.count(Student.id).desc(), Student.course.asc())
        ).all()
        year_stats = db.session.execute(
            select(Student.year_level, db.func.count(Student.id))
            .group_by(Student.year_level)
            .order_by(Student.year_level.asc())
        ).all()
        return render_template("reports.html", course_stats=course_stats, year_stats=year_stats)

    @app.get("/reports/export.csv")
    @login_required
    def export_students():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Student ID", "First name", "Middle name", "Last name", "Gender",
                "Date of birth", "Email", "Contact number", "Address", "Course", "Year level",
            ]
        )
        records = db.session.scalars(select(Student).order_by(Student.last_name, Student.first_name))
        for student in records:
            writer.writerow(
                _csv_safe(value)
                for value in [
                    student.student_id,
                    student.first_name,
                    student.middle_name or "",
                    student.last_name,
                    student.gender,
                    student.date_of_birth.isoformat(),
                    student.email,
                    student.contact_number,
                    student.address,
                    student.course,
                    student.year_level,
                ]
            )
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=student-records.csv"},
        )

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        form = SettingsForm()
        if form.validate_on_submit():
            admin = db.session.get(Admin, int(current_user.get_id()))
            if not admin or not admin.check_password(form.current_password.data):
                flash("Your current password is incorrect.", "error")
            elif form.current_password.data == form.new_password.data:
                flash("Choose a new password different from your current password.", "error")
            else:
                admin.set_password(form.new_password.data)
                db.session.commit()
                flash("Password updated successfully.", "success")
                return redirect(url_for("settings"))
        return render_template("settings.html", form=form)

    @app.get("/help")
    @login_required
    def help_page():
        return render_template("help.html")

    return app


def _populate_student(student, form):
    student.student_id = form.student_id.data.strip()
    student.first_name = form.first_name.data.strip()
    student.last_name = form.last_name.data.strip()
    student.middle_name = form.middle_name.data.strip() or None
    student.gender = form.gender.data
    student.date_of_birth = form.date_of_birth.data
    student.email = form.email.data.strip().lower()
    student.contact_number = form.contact_number.data.strip()
    student.address = form.address.data.strip()
    student.course = form.course.data
    student.year_level = int(form.year_level.data)


def _ensure_initial_admin():
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username and not password:
        return
    if not username or not password:
        raise click.ClickException("ADMIN_USERNAME and ADMIN_PASSWORD must both be configured.")
    if len(password) < 12:
        raise click.ClickException("ADMIN_PASSWORD must contain at least 12 characters.")
    if not db.session.scalar(select(Admin).where(Admin.username == username)):
        admin = Admin(username=username)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()


def _csv_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
