"""Public page behind a QR item tag (/t/<code>). Anyone who finds a tagged item can send
the owner a message; the owner's name and email are never shown."""
from flask import Blueprint, abort, current_app, render_template, request

from ..extensions import db, limiter
from ..models import ItemTag, utcnow
from ..services.audit import audit, notify
from ..services.messaging import send_email

bp = Blueprint("tags", __name__)


def _tag(code):
    tag = ItemTag.query.filter_by(code=code[:24]).first()
    if tag is None or not tag.is_active or tag.college.status != "active":
        abort(404)
    return tag


@bp.route("/t/<code>", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def scan(code):
    tag = _tag(code)
    college = tag.college
    if request.method == "GET":
        tag.scan_count += 1
        tag.last_scanned_at = utcnow()
        db.session.commit()
        return render_template("tag_scan.html", tag=tag, college=college, sent=False, error=None)

    message = request.form.get("message", "").strip()[:1000]
    contact = request.form.get("contact", "").strip()[:160]
    if len(message) < 5:
        return render_template("tag_scan.html", tag=tag, college=college, sent=False,
                               error="Write a short message so the owner knows where to find their item."), 400
    owner = tag.owner
    body = (f"Someone found your item tagged '{tag.label}' and sent this message:\n\n{message}\n\n"
            + (f"They left this way to reach them: {contact}\n\n" if contact else
               "They didn't leave contact details.\n\n")
            + "Your email address was not shown to them. Never share passwords or one-time codes "
              "with anyone who contacts you about an item.")
    notify(owner, "tag.found", f"Someone found your {tag.label}", message[:300], link="/me")
    audit("tag.message", tag, college_id=tag.college_id, actor=None, has_contact=bool(contact))
    db.session.commit()
    send_email(owner.email, f"Someone found your {tag.label}", body, college=college)
    current_app.logger.info("Tag message delivered for tag %s", tag.id)
    return render_template("tag_scan.html", tag=tag, college=college, sent=True, error=None)
