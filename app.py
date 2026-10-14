import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent


def load_local_environment():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_environment()

database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'spur.db'}")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_QR_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | {"pdf"}
COLLEGE_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def local_now():
    return datetime.now(COLLEGE_TIMEZONE).replace(tzinfo=None)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key"),
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    UPLOAD_FOLDER=str(BASE_DIR / "static" / "uploads"),
)
db = SQLAlchemy(app)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    roll_number = db.Column(db.String(40), unique=True, nullable=False)
    branch = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_token = db.Column(db.String(64))
    admin_requested = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    registrations = db.relationship("Registration", backref="student", cascade="all, delete-orphan")


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    venue = db.Column(db.String(180), nullable=False)
    branches = db.Column(db.String(500), nullable=False, default="All branches")
    description = db.Column(db.Text, nullable=False)
    club = db.Column(db.String(120), nullable=False, default="College community")
    capacity = db.Column(db.Integer)
    photos = db.Column(db.Text, default="")
    qr_file = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    registrations = db.relationship("Registration", backref="event", cascade="all, delete-orphan")

    @property
    def photo_list(self):
        return [name for name in (self.photos or "").split(",") if name]

    @property
    def participant_count(self):
        return sum(reg.participant_count for reg in self.registrations)


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    participant_names = db.Column(db.Text, nullable=False)
    participant_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    __table_args__ = (db.UniqueConstraint("student_id", "event_id", name="unique_student_event"),)


def valid_college_email(email):
    return email.strip().lower().endswith("@pvppcoe.ac.in")


def current_student():
    student_id = session.get("student_id")
    return db.session.get(Student, student_id) if student_id else None


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_student():
            if request.endpoint == "register" and kwargs.get("event_id"):
                session["after_login_event"] = kwargs["event_id"]
            flash("Please sign in to continue.", "error")
            return redirect(url_for("student_login"))
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        student = current_student()
        if not student or not student.is_admin:
            flash("This page is for approved admins.", "error")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped


def send_email(recipient, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:
        app.logger.info("Email preview to %s | %s\n%s", recipient, subject, body)
        return False
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM", "Spur Events <no-reply@pvppcoe.ac.in>")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as server:
        if os.environ.get("SMTP_USE_TLS", "true").lower() == "true":
            server.starttls()
        username = os.environ.get("SMTP_USERNAME")
        if username:
            server.login(username, os.environ.get("SMTP_PASSWORD", ""))
        server.send_message(message)
    return True


def save_upload(file, allowed):
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    if "." not in filename or filename.rsplit(".", 1)[1].lower() not in allowed:
        raise ValueError("Please upload a supported image or PDF file.")
    stored = f"{secrets.token_hex(12)}-{filename}"
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    file.save(Path(app.config["UPLOAD_FOLDER"]) / stored)
    return stored


@app.context_processor
def inject_user():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"current_user": current_student(), "now": local_now(), "csrf_token": session["csrf_token"]}


@app.before_request
def protect_forms():
    if request.method == "POST":
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            abort(400, "Form expired. Refresh the page and try again.")


@app.route("/")
def home():
    now = local_now()
    live = Event.query.filter(Event.start_at <= now, Event.end_at >= now).order_by(Event.start_at).all()
    upcoming = Event.query.filter(Event.start_at > now).order_by(Event.start_at).all()
    return render_template("home.html", live_events=live, upcoming_events=upcoming)


@app.route("/healthz")
def health_check():
    return {"status": "ok"}, 200


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        roll = request.form.get("roll_number", "").strip()
        branch = request.form.get("branch", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not valid_college_email(email):
            flash("Use your college email ending in @pvppcoe.ac.in.", "error")
        elif len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        elif not all([name, roll, branch]):
            flash("Please complete all profile details.", "error")
        elif Student.query.filter((Student.email == email) | (Student.roll_number == roll)).first():
            flash("That email or roll number is already registered.", "error")
        else:
            token = secrets.token_urlsafe(24)
            student = Student(name=name, roll_number=roll, branch=branch, email=email,
                              password_hash=generate_password_hash(password), verification_token=token)
            db.session.add(student)
            db.session.commit()
            verify_url = url_for("verify_email", token=token, _external=True)
            try:
                sent = send_email(email, "Verify your Spur account", f"Welcome to Spur! Verify your college email: {verify_url}")
            except (OSError, smtplib.SMTPException) as exc:
                app.logger.warning("Could not send verification email: %s", exc)
                sent = False
            if sent:
                flash("Account created. Check your college inbox for a verification link.", "success")
            else:
                flash("Account created. Email is not configured; use the verification link shown below for this demo.", "success")
                session["demo_verify_url"] = verify_url
            return redirect(url_for("student_login"))
    return render_template("signup.html")


@app.route("/verify/<token>")
def verify_email(token):
    student = Student.query.filter_by(verification_token=token).first_or_404()
    student.verified = True
    student.verification_token = None
    db.session.commit()
    flash("College email verified. You can now register for events.", "success")
    return redirect(url_for("student_login"))


@app.route("/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        student = Student.query.filter_by(email=email).first()
        if student and check_password_hash(student.password_hash, request.form.get("password", "")):
            event_id = session.pop("after_login_event", None)
            session.clear()
            session["student_id"] = student.id
            flash("Please verify your email before registering." if not student.verified else f"Welcome back, {student.name.split()[0]}!", "success")
            if event_id:
                return redirect(url_for("event_detail", event_id=event_id))
            return redirect(url_for("home"))
        flash("Email or password was not recognized.", "error")
    return render_template("login.html", admin=False, demo_verify_url=session.pop("demo_verify_url", None))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        student = Student.query.filter_by(email=email, is_admin=True).first()
        if student and check_password_hash(student.password_hash, request.form.get("password", "")):
            session.clear()
            session["student_id"] = student.id
            return redirect(url_for("admin_dashboard"))
        flash("Admin email or password was not recognized.", "error")
    return render_template("login.html", admin=True, demo_verify_url=None)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You are signed out.", "success")
    return redirect(url_for("home"))


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", registrations=Registration.query.filter_by(student_id=current_student().id).order_by(Registration.created_at.desc()).all())


@app.route("/admin/request", methods=["POST"])
@login_required
def request_admin():
    student = current_student()
    if not student.verified:
        flash("Verify your college email before requesting admin access.", "error")
    elif student.is_admin:
        flash("You already have admin access.", "success")
    else:
        student.admin_requested = True
        db.session.commit()
        flash("Admin access request sent for approval.", "success")
    return redirect(url_for("profile"))


@app.route("/events/<int:event_id>")
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    registered = False
    student = current_student()
    if student:
        registered = Registration.query.filter_by(event_id=event.id, student_id=student.id).first() is not None
    return render_template("event_detail.html", event=event, registered=registered)


@app.route("/events/<int:event_id>/preview")
def event_preview(event_id):
    event = db.get_or_404(Event, event_id)
    student = current_student()
    registered = bool(student and Registration.query.filter_by(event_id=event.id, student_id=student.id).first())
    return render_template("event_preview.html", event=event, registered=registered)


@app.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
def register(event_id):
    event = db.get_or_404(Event, event_id)
    student = current_student()
    if not student.verified:
        flash("Verify your college email before registering.", "error")
        return redirect(url_for("event_detail", event_id=event.id))
    if local_now() >= event.end_at:
        flash("Registration for this event has closed.", "error")
        return redirect(url_for("event_detail", event_id=event.id))
    if Registration.query.filter_by(event_id=event.id, student_id=student.id).first():
        flash("You are already registered for this event.", "error")
        return redirect(url_for("event_detail", event_id=event.id))
    names = [line.strip() for line in request.form.get("participant_names", "").splitlines() if line.strip()]
    try:
        count = int(request.form.get("participant_count", ""))
    except ValueError:
        count = 0
    if count < 1 or count > 20 or count != len(names):
        flash("Enter a name for each participant (1–20 participants).", "error")
    elif event.capacity and event.participant_count + count > event.capacity:
        flash("This event has reached its participant capacity.", "error")
    else:
        registration = Registration(student_id=student.id, event_id=event.id,
                                     participant_names="\n".join(names), participant_count=count)
        db.session.add(registration)
        db.session.commit()
        body = f"You are registered for {event.title}.\n\nParticipants:\n" + "\n".join(names) + f"\n\nDate: {event.start_at:%d %b %Y, %I:%M %p}\nVenue: {event.venue}"
        try:
            sent = send_email(student.email, f"Spur registration confirmed: {event.title}", body)
        except (OSError, smtplib.SMTPException) as exc:
            app.logger.warning("Could not send registration email: %s", exc)
            sent = False
        flash("Registration saved. A confirmation email has been sent." if sent else "Registration saved. Email delivery is unavailable; the confirmation is recorded in your profile.", "success")
        return redirect(url_for("profile"))
    return redirect(url_for("event_detail", event_id=event.id))


@app.route("/admin")
@admin_required
def admin_dashboard():
    events = Event.query.order_by(Event.start_at.desc()).all()
    requests = Student.query.filter_by(admin_requested=True, is_admin=False).order_by(Student.name).all()
    return render_template("admin_dashboard.html", events=events, admin_requests=requests)


@app.route("/admin/requests/<int:student_id>/approve", methods=["POST"])
@admin_required
def approve_admin(student_id):
    student = db.get_or_404(Student, student_id)
    student.admin_requested = False
    student.is_admin = True
    db.session.commit()
    flash(f"{student.name} is now an approved admin.", "success")
    return redirect(url_for("admin_dashboard"))


def event_form(event=None):
    data = request.form
    try:
        start_at = datetime.strptime(data.get("start_at", ""), "%Y-%m-%dT%H:%M")
        end_at = datetime.strptime(data.get("end_at", ""), "%Y-%m-%dT%H:%M")
        capacity = int(data.get("capacity") or 0) or None
    except ValueError:
        raise ValueError("Enter valid event dates and a whole-number capacity.")
    title, venue, description = data.get("title", "").strip(), data.get("venue", "").strip(), data.get("description", "").strip()
    if not title or not venue or not description or end_at <= start_at:
        raise ValueError("Add a title, venue, description, and an end time after the start time.")
    photo_names = event.photo_list[:] if event else []
    try:
        for photo in request.files.getlist("photos"):
            name = save_upload(photo, ALLOWED_IMAGE_EXTENSIONS)
            if name:
                photo_names.append(name)
        qr_file = save_upload(request.files.get("qr_file"), ALLOWED_QR_EXTENSIONS) or (event.qr_file if event else None)
    except ValueError:
        raise
    values = dict(title=title, start_at=start_at, end_at=end_at, venue=venue,
                  branches=data.get("branches", "All branches").strip() or "All branches",
                  description=description, club=data.get("club", "College community").strip() or "College community",
                  capacity=capacity, photos=",".join(photo_names), qr_file=qr_file)
    if event:
        for key, value in values.items():
            setattr(event, key, value)
    else:
        db.session.add(Event(**values))
    db.session.commit()


@app.route("/admin/events/new", methods=["GET", "POST"])
@admin_required
def create_event():
    if request.method == "POST":
        try:
            event_form()
            flash("Event published to Spur.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("event_form.html", event=None)


@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_event(event_id):
    event = db.get_or_404(Event, event_id)
    if request.method == "POST":
        try:
            event_form(event)
            flash("Event details updated.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("event_form.html", event=event)


@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def delete_event(event_id):
    event = db.get_or_404(Event, event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(413)
def upload_too_large(_error):
    flash("Uploads must be smaller than 12 MB.", "error")
    return redirect(request.referrer or url_for("home"))


def initialize():
    with app.app_context():
        db.create_all()
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
        if email and password and valid_college_email(email):
            admin = Student.query.filter_by(email=email).first()
            if admin:
                admin.password_hash = generate_password_hash(password)
                admin.verified = True
                admin.is_admin = True
                admin.admin_requested = False
            else:
                db.session.add(Student(name="Spur Admin", roll_number=f"ADMIN-{secrets.token_hex(4)}",
                                       branch="Other", email=email, password_hash=generate_password_hash(password),
                                       verified=True, is_admin=True))
            Student.query.filter(Student.is_admin.is_(True), Student.email != email).update(
                {Student.is_admin: False}, synchronize_session=False
            )
            db.session.commit()


initialize()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
