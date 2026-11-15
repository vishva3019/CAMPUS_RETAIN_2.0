"""Operator commands: ``flask rbac|college|user|legacy ...``"""
import click
from flask.cli import AppGroup
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import (Campus, Claim, ClaimStatus, College, CollegeStatus, Item,
                     ItemStatus, User, utcnow)
from .security import PLATFORM_SUPER_ADMIN, ROLES, STUDENT, get_role, sync_roles
from .services.audit import audit

rbac_cli = AppGroup("rbac", help="Roles and permissions.")
college_cli = AppGroup("college", help="Manage colleges.")
user_cli = AppGroup("user", help="Manage user accounts.")
legacy_cli = AppGroup("legacy", help="Upgrade a Campus Retain 2.0 database.")
storage_cli = AppGroup("storage", help="Photo storage.")
push_cli = AppGroup("push", help="Browser push notifications.")
mail_cli = AppGroup("mail", help="Outgoing email.")
claims_cli = AppGroup("claims", help="Claims and pickups.")


@claims_cli.command("remind-pickups")
def claims_remind_pickups():
    """Remind students once about approved items they haven't collected yet."""
    from .services.claims import send_pickup_reminders
    click.echo(f"Sent {send_pickup_reminders()} pickup reminder(s).")


@mail_cli.command("test")
@click.option("--to", "to", required=True, help="Address to send a test message to")
def mail_test(to):
    """Send one test email with the current MAIL_* settings and report the result."""
    from flask import current_app

    from .services.messaging import send_email
    cfg = current_app.config
    click.echo(f"Backend: {cfg['MAIL_BACKEND']}  server: {cfg['MAIL_SERVER']}:{cfg['MAIL_PORT']}  "
               f"user: {cfg.get('MAIL_USERNAME') or '(not set)'}  password: {'set' if cfg.get('MAIL_PASSWORD') else 'not set'}")
    ok = send_email(to, "Campus Retain test email",
                    "This is a test from Campus Retain. If you can read it, outgoing email works.")
    if not ok:
        raise click.ClickException("Not sent. Check MAIL_USERNAME / MAIL_PASSWORD (a Gmail App Password) and the log above.")
    click.echo("Sent." if cfg["MAIL_BACKEND"] == "smtp" else f"Not really sent: MAIL_BACKEND is {cfg['MAIL_BACKEND']}.")


@push_cli.command("vapid-keys")
def push_vapid_keys():
    """Print a new VAPID key pair for VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.

    Keep the private key secret (set it only in the hosting provider's env settings).
    Changing keys later means every browser has to subscribe again."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid02
    v = Vapid02()
    v.generate_keys()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    click.echo(f"VAPID_PUBLIC_KEY={b64(pub)}")
    click.echo(f"VAPID_PRIVATE_KEY={b64(priv)}")
    click.echo("VAPID_SUBJECT=mailto:you@example.com   # a contact address push services can reach")


@rbac_cli.command("sync")
def rbac_sync():
    """Create or update the built-in roles and permissions."""
    sync_roles()
    click.echo("Roles and permissions are up to date.")


@college_cli.command("create")
@click.option("--name", required=True)
@click.option("--slug", required=True, help="URL id, e.g. mvj-ce")
@click.option("--domain", "domains", multiple=True, required=True, help="Email domain (repeatable)")
@click.option("--short-name")
@click.option("--city")
@click.option("--contact-email")
@click.option("--support-office")
@click.option("--pickup-instructions")
@click.option("--active/--pending", default=False, help="Activate immediately (default: pending)")
def college_create(name, slug, domains, active, **fields):
    from .blueprints.platform import create_college, parse_domains

    parsed, bad = parse_domains(" ".join(domains))
    if bad:
        raise click.ClickException("Invalid domain: " + ", ".join(bad))
    try:
        college = create_college(name, slug, parsed,
                                 status=CollegeStatus.ACTIVE if active else CollegeStatus.PENDING,
                                 **fields)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    db.session.commit()
    click.echo(f"Created college #{college.id} '{college.slug}' ({college.status}).")


@college_cli.command("onboard")
@click.option("--name", required=True)
@click.option("--slug", required=True)
@click.option("--domain", required=True, help="The one student email domain, e.g. mvjce.edu.in")
@click.option("--short-name")
@click.option("--city")
@click.option("--color", help="Card colour as #rrggbb")
@click.option("--logo-url", help="https:// link to the official logo (optional)")
def college_onboard(name, slug, domain, short_name, city, color, logo_url):
    """Create or update a college and list it on the sign-up screen. Safe to re-run:
    an existing college (same slug) is updated, never duplicated."""
    import re

    from .blueprints.platform import create_college, parse_domains
    from .models import CollegeDomain

    parsed, bad = parse_domains(domain)
    if bad or len(parsed) != 1:
        raise click.ClickException("Give exactly one valid email domain.")
    domain = parsed[0]
    if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise click.ClickException("--color must look like #1d4ed8.")
    if logo_url and not logo_url.startswith("https://"):
        raise click.ClickException("--logo-url must start with https://")
    college = College.query.filter_by(slug=slug).first()
    owner = CollegeDomain.query.filter_by(domain=domain).first()
    if owner is not None and (college is None or owner.college_id != college.id):
        raise click.ClickException(f"{domain} already belongs to college #{owner.college_id}.")
    if college is None:
        try:
            college = create_college(name, slug, parsed, status=CollegeStatus.ACTIVE,
                                     short_name=short_name, city=city)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        action = "Created"
    else:
        college.name = name
        if short_name:
            college.short_name = short_name
        if city:
            college.city = city
        if owner is None:
            college.domains.append(CollegeDomain(domain=domain))
        if college.status != CollegeStatus.ACTIVE:
            click.echo(f"Note: {slug} is {college.status}; it appears on the sign-up screen once active.")
        action = "Updated"
    if color:
        college.primary_color = color.lower()
    if logo_url:
        college.logo_url = logo_url
    college.listed_on_signup = True
    audit("college.signup_listing", college, college_id=college.id, listed=True, via="cli")
    db.session.commit()
    click.echo(f"{action} #{college.id} {college.slug}: {college.name} [{', '.join(d.domain for d in college.domains)}], listed on sign-up.")


@college_cli.command("set-status")
@click.argument("slug")
@click.argument("status", type=click.Choice(CollegeStatus.ALL))
def college_set_status(slug, status):
    college = College.query.filter_by(slug=slug).first()
    if not college:
        raise click.ClickException(f"No college '{slug}'.")
    old, college.status = college.status, status
    audit("college.status_changed", college, college_id=college.id, old=old, new=status, via="cli")
    db.session.commit()
    click.echo(f"{college.slug}: {old} -> {status}")


@college_cli.command("add-campus")
@click.argument("slug")
@click.argument("name")
@click.option("--address")
def college_add_campus(slug, name, address):
    college = College.query.filter_by(slug=slug).first()
    if not college:
        raise click.ClickException(f"No college '{slug}'.")
    if Campus.query.filter_by(college_id=college.id, name=name).first():
        raise click.ClickException("That campus already exists.")
    db.session.add(Campus(college_id=college.id, name=name, address=address))
    db.session.commit()
    click.echo(f"Added campus '{name}' to {slug}.")


@college_cli.command("list")
def college_list():
    for c in College.query.order_by(College.id).all():
        click.echo(f"#{c.id:<4} {c.slug:<20} {c.status:<10} {c.name}  [{', '.join(d.domain for d in c.domains)}]")


@user_cli.command("create")
@click.option("--email", required=True)
@click.option("--role", required=True, type=click.Choice(sorted(ROLES)))
@click.option("--college", "college_slug", help="Required for every role except platform_super_admin")
@click.option("--campus", "campus_name")
@click.password_option()
def user_create(email, role, college_slug, campus_name, password):
    """Create a verified account (staff and platform admins)."""
    email = email.strip().lower()
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("That email already has an account.")
    college = campus = None
    if role == PLATFORM_SUPER_ADMIN:
        if college_slug:
            raise click.ClickException("Platform admins don't belong to a college.")
    else:
        college = College.query.filter_by(slug=college_slug).first() if college_slug else None
        if not college:
            raise click.ClickException("--college is required and must exist.")
        if campus_name:
            campus = Campus.query.filter_by(college_id=college.id, name=campus_name).first()
            if not campus:
                raise click.ClickException("Unknown campus.")
    user = User(email=email, password=generate_password_hash(password), role_id=get_role(role).id,
                college_id=college.id if college else None, campus_id=campus.id if campus else None,
                email_verified_at=utcnow(), created_at=utcnow())
    db.session.add(user)
    db.session.flush()
    audit("user.created", user, actor=None, college_id=user.college_id, role=role, via="cli")
    db.session.commit()
    click.echo(f"Created {role} {email}.")


@legacy_cli.command("adopt")
@click.option("--slug", required=True, help="College that owns the 2.0 data (create it first).")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def legacy_adopt(slug, yes):
    """Assign all 2.0 rows (college_id IS NULL) to one college and convert claim history.

    Safe to re-run: only rows without a college are touched.
    """
    college = College.query.filter_by(slug=slug).first()
    if not college:
        raise click.ClickException(f"No college '{slug}'. Run 'flask college create' first.")

    users = User.query.filter(User.college_id.is_(None), User.role_id.is_(None)).all()
    from sqlalchemy.orm import load_only
    # Runs at revision 0002: load only columns that exist then.
    items = (Item.query.filter(Item.college_id.is_(None))
             .options(load_only(Item.id, Item.college_id, Item.kind, Item.status)).all())
    items_by_id = {i.id: i for i in items}
    # Runs at revision 0002, before later columns exist: load only the columns it touches.
    claims = (Claim.query.filter(Claim.college_id.is_(None))
              .options(load_only(Claim.id, Claim.item_id, Claim.student_email, Claim.timestamp,
                                 Claim.college_id, Claim.claimant_id, Claim.status, Claim.review_remarks))
              .all())
    click.echo(f"Will assign to '{college.slug}': {len(users)} users, {len(items)} items, {len(claims)} claims.")
    if not yes:
        click.confirm("Have you taken a database backup?", abort=True)

    student = get_role(STUDENT)
    for u in users:
        u.college_id, u.role_id = college.id, student.id   # email_verified_at stays NULL: verify on next login
    by_email = {u.email: u.id for u in User.query.filter_by(college_id=college.id)}

    for item in items:
        item.college_id = college.id
        item.kind = item.kind or "found"
        item.status = item.status or ItemStatus.AVAILABLE
    db.session.flush()

    # 2.0 kept no per-claim outcome. The latest claim inherits the item's state;
    # older claims are closed with a note so history is preserved but not misread.
    claims_by_item = {}
    for c in claims:
        c.college_id = college.id
        c.claimant_id = by_email.get((c.student_email or "").strip().lower())
        claims_by_item.setdefault(c.item_id, []).append(c)
    for item_id, group in claims_by_item.items():
        group.sort(key=lambda c: (c.timestamp or utcnow(), c.id))
        item = items_by_id.get(item_id) or (Item.query.options(load_only(Item.id, Item.status))
                                             .filter(Item.id == item_id).one())
        for c in group:
            c.status = ClaimStatus.CLOSED
            c.review_remarks = "Imported from Campus Retain 2.0 (outcome not recorded)."
        latest = group[-1]
        if item.status == ItemStatus.PENDING:
            latest.status, latest.review_remarks = ClaimStatus.PENDING, None
        elif item.status == ItemStatus.CLAIMED:
            latest.status = ClaimStatus.APPROVED
            latest.review_remarks = "Approved in Campus Retain 2.0."

    # Items marked Pending with no claim at all cannot be reviewed: make them available again.
    for item in items:
        if item.status == ItemStatus.PENDING and item.id not in claims_by_item:
            item.status = ItemStatus.AVAILABLE

    audit("legacy.adopted", college, college_id=college.id, actor=None,
          users=len(users), items=len(items), claims=len(claims))
    db.session.commit()
    remaining = db.session.query(func.count(Item.id)).filter(Item.college_id.is_(None)).scalar()
    db.session.remove()  # end the read transaction so the next migration can take its locks
    click.echo(f"Done. Items still without a college: {remaining}. "
               "Next: 'flask db upgrade' to enforce college_id NOT NULL.")


@storage_cli.command("move-legacy-photos")
@click.option("--limit", type=int, default=0, help="Stop after this many items (0 = all).")
@click.option("--dry-run", is_flag=True, help="Count only; change nothing.")
def storage_move_legacy_photos(limit, dry_run):
    """Move 2.0 photos (base64 in item.image_data) to object storage.

    Each item is committed on its own, so the command can be stopped and re-run."""
    import base64
    import binascii

    from .models import ItemImage
    from .services.storage import StorageError, get_storage, new_key

    store = get_storage()
    if store is None:
        raise click.ClickException("STORAGE_BACKEND is 'database'. Configure R2 first (see docs/DEPLOYMENT.md).")
    query = Item.query.filter(Item.image_data.isnot(None), Item.image_data != "").order_by(Item.id)
    total = query.count()
    click.echo(f"{total} items have a photo stored in the database.")
    if dry_run or not total:
        return
    moved = skipped = 0
    for item_id in [i for (i,) in query.with_entities(Item.id).limit(limit or None).all()]:
        item = db.session.get(Item, item_id)
        header, _, payload = (item.image_data or "").partition(",")
        content_type = header[5:].split(";")[0] if header.startswith("data:") else ""
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            data = b""
        if not data or not content_type.startswith("image/"):
            click.echo(f"  item {item.id}: not a valid inline photo, left as is")
            skipped += 1
            db.session.rollback()
            continue
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(content_type, "img")
        key = new_key(item.college_id, ext)
        try:
            store.put(key, data, content_type)
        except StorageError as exc:
            raise click.ClickException(f"Upload failed at item {item.id}: {exc}. Nothing else was changed; re-run to continue.")
        item.images.insert(0, ItemImage(college_id=item.college_id, storage_key=key, content_type=content_type,
                                        size_bytes=len(data), position=0))
        for i, img in enumerate(item.images):
            img.position = i
        item.image_data = None
        audit("storage.photo_moved", item, actor=None, storage_key=key)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            store.delete(key)
            raise
        moved += 1
    click.echo(f"Moved {moved} photo(s); skipped {skipped}.")
    db.session.remove()


def register_cli(app):
    for group in (rbac_cli, college_cli, user_cli, legacy_cli, storage_cli, push_cli, mail_cli, claims_cli):
        app.cli.add_command(group)
