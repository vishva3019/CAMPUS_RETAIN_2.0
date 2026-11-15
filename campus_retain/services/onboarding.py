"""Validation for the animated sign-up and sign-in screens.

The college a student picks only decides which email domain is *expected*. The domain
list always comes from the college record in the database, and the check is exact:
``student@ced.alliance.edu.in`` belongs to the college whose domain is
``ced.alliance.edu.in``, and nothing else does.
"""
import re
import unicodedata

from flask import current_app

from ..models import College, CollegeStatus, Department

YEARS = {"1": "1st Year", "2": "2nd Year", "3": "3rd Year", "4": "4th Year", "other": "Other"}

_LOCAL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9_%+-])?$")
_STUDENT_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9/-]{2,29}$")
_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ .'\-][^\W\d_]*)*$")
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123",
    "qwertyuiop", "iloveyou", "11111111", "00000000", "abcd1234", "admin123", "welcome1",
    "letmein1", "campusretain", "college123", "student123",
}


class OnboardingError(ValueError):
    def __init__(self, message, field=None, status=400):
        super().__init__(message)
        self.field = field
        self.status = status


def normalize_email(raw):
    """NFKC, trim, lowercase. Returns '' for anything that isn't a plain address."""
    email = unicodedata.normalize("NFKC", str(raw or "")).strip().lower()
    if len(email) > 120 or email.count("@") != 1 or any(c.isspace() for c in email):
        return ""
    local, domain = email.split("@")
    if not _LOCAL_RE.match(local) or ".." in local or not domain or ".." in domain:
        return ""
    return email


def signup_colleges():
    """Colleges shown on the public screens: active and chosen by the platform admin."""
    return (College.query.filter_by(status=CollegeStatus.ACTIVE, listed_on_signup=True)
            .order_by(College.name).all())


def college_card(c):
    return {"id": c.id, "slug": c.slug, "name": c.name, "short_name": c.short_name, "city": c.city,
            "logo_url": c.logo_url, "primary_color": c.primary_color or "#5b21b6",
            "domains": [d.domain for d in c.domains]}


def active_college(college_id, listed=True):
    try:
        college_id = int(college_id)
    except (TypeError, ValueError):
        raise OnboardingError("Choose your college.", "college")
    query = College.query.filter_by(id=college_id, status=CollegeStatus.ACTIVE)
    if listed:
        query = query.filter_by(listed_on_signup=True)
    college = query.first()
    if college is None:
        raise OnboardingError("That college isn't accepting sign-ups on Campus Retain right now.", "college")
    return college


def domain_message(college):
    domains = [d.domain for d in college.domains]
    ending = " or ".join(f"@{d}" for d in domains) or "its official domain"
    return f"Please enter your official {college.name} email address ending with {ending}."


def college_email(raw, college):
    """Normalised email if it is on one of this college's domains, else OnboardingError."""
    email = normalize_email(raw)
    if not email:
        raise OnboardingError("Enter a valid email address.", "email")
    domain = email.rsplit("@", 1)[1]
    if domain not in {d.domain.lower() for d in college.domains}:
        raise OnboardingError(domain_message(college), "email")
    return email


def clean_name(raw):
    name = " ".join(unicodedata.normalize("NFKC", str(raw or "")).split())
    if len(name) < 2 or len(name) > 120:
        raise OnboardingError("Enter your full name.", "full_name")
    if not _NAME_RE.match(name):
        raise OnboardingError("Use letters only in your name (spaces, dots, hyphens and apostrophes are fine).", "full_name")
    return name


def clean_student_id(raw):
    sid = "".join(unicodedata.normalize("NFKC", str(raw or "")).split()).upper()
    if not _STUDENT_ID_RE.match(sid):
        raise OnboardingError("Enter your student ID or USN as printed on your ID card (letters and numbers).", "student_id")
    return sid


def clean_department(raw, college):
    """(department_id or None, name). Matches a department the college has set up, else
    keeps the typed name: colleges name their departments differently."""
    name = " ".join(unicodedata.normalize("NFKC", str(raw or "")).split())
    if len(name) < 2 or len(name) > 120 or any(c in name for c in "<>"):
        raise OnboardingError("Enter your department.", "department")
    match = next((d for d in Department.query.filter_by(college_id=college.id).all()
                  if d.name.lower() == name.lower()), None)
    return (match.id, match.name) if match else (None, name)


def clean_year(raw):
    year = str(raw or "").strip().lower()
    if year not in YEARS:
        raise OnboardingError("Choose your current year of study.", "year_of_study")
    return year


def check_new_password(password, email="", student_id=""):
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if not isinstance(password, str) or len(password) < minimum:
        raise OnboardingError(f"Use at least {minimum} characters for your password.", "password")
    if len(password) > 128:
        raise OnboardingError("Use at most 128 characters for your password.", "password")
    lowered = password.lower()
    local = email.split("@", 1)[0] if email else ""
    if (lowered in _COMMON_PASSWORDS or len(set(password)) < 4
            or (len(local) >= 4 and local in lowered)
            or (student_id and student_id.lower() in lowered)):
        raise OnboardingError("That password is too easy to guess. Avoid your email, USN and common passwords.", "password")
    return password


def department_suggestions(college):
    return [d.name for d in Department.query.filter_by(college_id=college.id).order_by(Department.name).all()]
