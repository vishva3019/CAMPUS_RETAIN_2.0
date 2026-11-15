"""Database models.

Tenancy rule: every college-owned row carries ``college_id``. Queries for
college data must go through ``campus_retain.security.tenant_query`` (or filter on
``college_id`` explicitly), never on an id taken from the browser alone.

Legacy 2.0 tables (``user``, ``item``, ``claim``) keep their names and original
columns so the production database can be upgraded in place.
"""
from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from .extensions import db

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in quick tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow():
    # Naive UTC, matching the 2.0 columns (timestamp without time zone).
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- statuses

class CollegeStatus:
    PENDING = "pending"      # registered, awaiting platform approval
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ALL = (PENDING, ACTIVE, SUSPENDED)


class ItemStatus:
    # Values kept identical to 2.0 so existing rows need no rewrite.
    AVAILABLE = "Available"   # found item waiting for its owner
    PENDING = "Pending"       # a claim is under review
    CLAIMED = "Claimed"       # claim approved, waiting for pickup
    RETURNED = "Returned"     # handed over (Phase 2: confirmed by pickup OTP)
    REMOVED = "Removed"       # hidden by an admin; history kept
    VISIBLE = (AVAILABLE, PENDING, CLAIMED, RETURNED)


class ItemKind:
    FOUND = "found"
    LOST = "lost"


class ClaimStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    COLLECTED = "collected"
    CLOSED = "closed"         # imported from 2.0 where the outcome was not recorded
    ACTIVE = (PENDING, APPROVED)


# ---------------------------------------------------------------- tenancy

class College(db.Model):
    __tablename__ = "college"
    __mapper_args__ = {"eager_defaults": False}   # don't RETURNING listed_on_signup (see below)

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    short_name = db.Column(db.String(40))
    city = db.Column(db.String(80))
    status = db.Column(db.String(20), nullable=False, default=CollegeStatus.PENDING)

    # Branding
    primary_color = db.Column(db.String(9), default="#5b21b6")
    logo_url = db.Column(db.String(500))

    # Contact + operations (shown to students; no secrets here)
    contact_email = db.Column(db.String(160))
    support_office = db.Column(db.String(160))
    pickup_instructions = db.Column(db.Text)
    mail_from_name = db.Column(db.String(120))

    inter_college_matching = db.Column(db.Boolean, nullable=False, default=False)
    # Shown as a card on the public sign-up and sign-in screens (platform admin decides).
    # Deferred and server-defaulted so the 2.0 upgrade commands (which run before migration
    # 0009 adds it) never select or insert it.
    listed_on_signup = db.deferred(db.Column(db.Boolean, nullable=False, server_default=text("false")))

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    domains = db.relationship("CollegeDomain", backref="college", lazy="selectin",
                              cascade="all, delete-orphan", order_by="CollegeDomain.domain")
    campuses = db.relationship("Campus", backref="college", lazy="selectin",
                               order_by="Campus.name")

    @property
    def is_active(self):
        return self.status == CollegeStatus.ACTIVE

    @property
    def display_name(self):
        return self.short_name or self.name


class CollegeDomain(db.Model):
    """Email domains that belong to a college, e.g. ``ced.alliance.edu.in``."""
    __tablename__ = "college_domain"

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = db.Column(db.String(160), unique=True, nullable=False)


class Campus(db.Model):
    __tablename__ = "campus"
    __table_args__ = (UniqueConstraint("college_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(300))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Department(db.Model):
    __tablename__ = "department"
    __table_args__ = (UniqueConstraint("college_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campus.id", ondelete="SET NULL"), index=True)
    name = db.Column(db.String(120), nullable=False)


# ---------------------------------------------------------------- access control

role_permissions = db.Table(
    "role_permission",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(db.Model):
    __tablename__ = "permission"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    description = db.Column(db.String(200))


class Role(db.Model):
    __tablename__ = "role"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    label = db.Column(db.String(80), nullable=False)
    is_platform = db.Column(db.Boolean, nullable=False, default=False)

    permissions = db.relationship("Permission", secondary=role_permissions, lazy="selectin")

    def permission_codes(self):
        return {p.code for p in self.permissions}


class User(db.Model):
    __tablename__ = "user"
    __table_args__ = (
        # One account per student ID within a college (NULL for staff and 2.0 accounts).
        Index("uq_user_college_student_id", "college_id", "student_id", unique=True,
              postgresql_where=text("student_id IS NOT NULL")),
    )

    # 2.0 columns
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    # 3.0 columns (nullable at DB level so the 2.0 table can be upgraded in place)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), index=True)  # NULL only for platform admins
    campus_id = db.Column(db.Integer, db.ForeignKey("campus.id", ondelete="SET NULL"), index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id", ondelete="SET NULL"))
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), index=True)
    full_name = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    # Onboarding details (migration 0009). Deferred (loaded together on first use) so the
    # 2.0 upgrade commands, which run before 0009, never select them.
    student_id = db.deferred(db.Column(db.String(30)), group="onboarding")        # USN, unique per college
    department_name = db.deferred(db.Column(db.String(120)), group="onboarding")  # as typed at registration
    year_of_study = db.deferred(db.Column(db.String(10)), group="onboarding")     # 1, 2, 3, 4 or other

    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=text("true"))
    email_verified_at = db.Column(db.DateTime)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    locked_until = db.Column(db.DateTime)
    session_version = db.Column(db.Integer, nullable=False, default=1, server_default=text("1"))
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    college = db.relationship("College", lazy="joined")
    campus = db.relationship("Campus")
    role = db.relationship("Role", lazy="joined")

    @property
    def is_verified(self):
        return self.email_verified_at is not None

    @property
    def role_name(self):
        return self.role.name if self.role else None

    def has_permission(self, code):
        return bool(self.role) and code in self.role.permission_codes()


# ---------------------------------------------------------------- lost & found

class CollectionPoint(db.Model):
    __tablename__ = "collection_point"

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campus.id", ondelete="SET NULL"), index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    opening_hours = db.Column(db.String(160))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    campus = db.relationship("Campus")

    def pickup_text(self):
        text_ = f"Collect it from {self.name}"
        if self.campus:
            text_ += f" ({self.campus.name} campus)"
        if self.opening_hours:
            text_ += f", open {self.opening_hours}"
        return text_ + "."


class Event(db.Model):
    """Temporary lost-and-found portal (fest, hackathon, sports meet). Phase 6."""
    __tablename__ = "event"
    __table_args__ = (UniqueConstraint("college_id", "slug"),)

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campus.id", ondelete="SET NULL"))
    slug = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    campus = db.relationship("Campus")

    def is_open(self, now=None):
        """Reports can be tagged with the event from a day before it starts to a week after."""
        from datetime import timedelta
        now = now or utcnow()
        return self.is_active and self.starts_at - timedelta(days=1) <= now <= self.ends_at + timedelta(days=7)


class ItemTag(db.Model):
    """A QR sticker a student puts on their belongings (Phase 6). Whoever finds the item
    scans it and can message the owner without seeing who they are."""
    __tablename__ = "item_tag"

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    code = db.Column(db.String(24), nullable=False, unique=True)
    label = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=text("true"))
    scan_count = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    last_scanned_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User")
    college = db.relationship("College")


class Item(db.Model):
    __tablename__ = "item"
    __table_args__ = (
        Index("ix_item_college_status_date", "college_id", "status", "date_found"),
    )

    # 2.0 columns
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(150))
    secret_detail = db.Column(db.Text)            # visible to staff only, never to claimants
    image_data = db.Column(db.Text)               # 2.0 base64 photo; replaced by ItemImage in Phase 2
    status = db.Column(db.String(30), default=ItemStatus.AVAILABLE)
    date_found = db.Column(db.DateTime, default=utcnow)   # report timestamp in 2.0

    # 3.0 columns (college_id becomes NOT NULL in migration 0003, after legacy adoption)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campus.id", ondelete="SET NULL"), index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id", ondelete="SET NULL"), index=True)
    collection_point_id = db.Column(db.Integer, db.ForeignKey("collection_point.id", ondelete="SET NULL"))
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    kind = db.Column(db.String(10), nullable=False, default=ItemKind.FOUND, server_default=ItemKind.FOUND)
    description = db.Column(db.Text)
    occurred_on = db.Column(db.Date)              # day found / lost (as reported)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    removed_at = db.Column(db.DateTime)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    # Approximate place (Phase 6), rounded to 3 decimals (~100 m) before saving.
    latitude = db.Column(db.Numeric(8, 5))
    longitude = db.Column(db.Numeric(8, 5))

    # No delete cascade: claim history must survive.
    claims = db.relationship("Claim", backref="item", lazy="select",
                             order_by="Claim.timestamp", passive_deletes="all")
    images = db.relationship("ItemImage", backref="item", lazy="select",
                             cascade="all, delete-orphan", order_by="ItemImage.position")
    campus = db.relationship("Campus")
    college = db.relationship("College")
    event = db.relationship("Event")
    reported_by = db.relationship("User", foreign_keys=[reported_by_id])
    collection_point = db.relationship("CollectionPoint")

    @property
    def has_photo(self):
        return bool(self.images) or bool(self.image_data)

    @property
    def active_claim(self):
        for claim in self.claims:
            if claim.status in ClaimStatus.ACTIVE:
                return claim
        return None


class ItemImage(db.Model):
    """Photo stored in object storage (Phase 2). Only the key/URL and metadata live here."""
    __tablename__ = "item_image"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id", ondelete="CASCADE"), nullable=False, index=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
    storage_key = db.Column(db.String(400), nullable=False, unique=True)
    content_type = db.Column(db.String(40), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Claim(db.Model):
    __tablename__ = "claim"
    __table_args__ = (
        # Database-level guarantee: at most one active (pending/approved) claim per item.
        Index("uq_claim_one_active_per_item", "item_id", unique=True,
              postgresql_where=text("status IN ('pending', 'approved')"),
              sqlite_where=text("status IN ('pending', 'approved')")),
    )

    # 2.0 columns
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False, index=True)
    student_id = db.Column(db.String(50))        # student's college ID number, as typed
    student_email = db.Column(db.String(120))    # copy of the claimant's verified email
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=utcnow)

    # 3.0 columns
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
    claimant_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    status = db.Column(db.String(20), nullable=False, default=ClaimStatus.PENDING, server_default=ClaimStatus.PENDING)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    review_remarks = db.Column(db.Text)

    # Pickup (Phase 2): a one-time code is emailed on approval; staff check it at handover.
    pickup_code_hash = db.Column(db.String(255))
    pickup_code_sent_at = db.Column(db.DateTime)
    pickup_code_expires_at = db.Column(db.DateTime)
    pickup_code_attempts = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    collected_at = db.Column(db.DateTime)
    collected_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    # Migration 0010. Deferred so the 2.0 upgrade commands never select it.
    pickup_reminded_at = db.deferred(db.Column(db.DateTime))

    claimant = db.relationship("User", foreign_keys=[claimant_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    collected_by = db.relationship("User", foreign_keys=[collected_by_id])


class PushSubscription(db.Model):
    """A browser that agreed to receive push notifications for a user (Phase 7)."""
    __tablename__ = "push_subscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(100), nullable=False)
    user_agent = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_success_at = db.Column(db.DateTime)


class MatchStatus:
    SUGGESTED = "suggested"
    DISMISSED = "dismissed"     # the lost item's owner said it isn't theirs
    CONFIRMED = "confirmed"     # a claim on the found item by that owner was approved


class ItemMatch(db.Model):
    """A suggested pairing of a found item with a lost report, scored by text similarity
    (Phase 5). An optional AI check adds a verdict, but staff and owners always decide."""
    __tablename__ = "item_match"
    __table_args__ = (UniqueConstraint("found_item_id", "lost_item_id", name="uq_item_match_pair"),)

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    found_item_id = db.Column(db.Integer, db.ForeignKey("item.id", ondelete="CASCADE"), nullable=False, index=True)
    lost_item_id = db.Column(db.Integer, db.ForeignKey("item.id", ondelete="CASCADE"), nullable=False, index=True)
    score = db.Column(db.Float, nullable=False)
    reasons = db.Column(JSONType)
    status = db.Column(db.String(20), nullable=False, default=MatchStatus.SUGGESTED, server_default=MatchStatus.SUGGESTED)
    notified_at = db.Column(db.DateTime)
    ai_verdict = db.Column(db.String(20))        # likely | unlikely | unsure
    ai_reason = db.Column(db.Text)
    ai_checked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    found_item = db.relationship("Item", foreign_keys=[found_item_id])
    lost_item = db.relationship("Item", foreign_keys=[lost_item_id])


# ---------------------------------------------------------------- operations

class Notification(db.Model):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_unread", "user_id", "read_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), index=True)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    link = db.Column(db.String(300))
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_college_created", "college_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="SET NULL"))
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    actor_email = db.Column(db.String(160))
    action = db.Column(db.String(60), nullable=False, index=True)
    target_type = db.Column(db.String(40))
    target_id = db.Column(db.Integer)
    ip_address = db.Column(db.String(64))
    details = db.Column(JSONType)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Subscription(db.Model):
    """College plan. Billing integration is Phase 7; until then plans are set by platform admins."""
    __tablename__ = "subscription"

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    plan = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False)        # trialing | active | past_due | cancelled
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    external_ref = db.Column(db.String(120))                 # billing provider id
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class PlatformSetting(db.Model):
    __tablename__ = "platform_setting"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(JSONType)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class PendingRegistration(db.Model):
    """Details from the sign-up form, held until the email code is confirmed. The account
    (User row) is created only after verification, so nobody can reserve someone else's
    email address. Expires with the code; replaced if the student starts again."""
    __tablename__ = "pending_registration"

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id", ondelete="CASCADE"), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    full_name = db.Column(db.String(120), nullable=False)
    student_id = db.Column(db.String(30), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id", ondelete="SET NULL"))
    department_name = db.Column(db.String(120), nullable=False)
    year_of_study = db.Column(db.String(10), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    college = db.relationship("College")


class EmailCode(db.Model):
    """Hashed one-time codes for email verification and password reset."""
    __tablename__ = "email_code"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False)       # signup | reset | verify
    code_hash = db.Column(db.String(255), nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
