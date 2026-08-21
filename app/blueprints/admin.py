"""Administrator login and dashboard."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models import Claim, ClaimStatus, Item, ItemStatus
from app.security import (
    admin_required,
    normalise_email,
    start_admin_session,
    verify_admin_credentials,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin/login.html")

    email = normalise_email(request.form.get("email"))
    password = request.form.get("password") or ""

    if not verify_admin_credentials(email, password):
        # Deliberately vague, and identical whether the email or the password
        # was wrong.
        flash("Invalid administrator credentials.", "error")
        return render_template("admin/login.html"), 401

    start_admin_session(email)
    return redirect(url_for("admin.dashboard"))


@bp.route("/")
@admin_required
def dashboard():
    """Review queue plus the full register.

    Pending claims come first because they are the only thing on this page that
    needs a human decision. Each one is shown beside the finder's private note
    so the two descriptions can be compared without another click.
    """
    pending_claims = (
        Claim.query.filter_by(status=ClaimStatus.PENDING)
        .order_by(Claim.created_at.asc())
        .all()
    )

    page = request.args.get("page", type=int, default=1)
    pagination = (
        Item.query.order_by(Item.date_found.desc())
        .paginate(
            page=max(1, page),
            per_page=current_app.config["ITEMS_PER_PAGE"] * 2,
            error_out=False,
        )
    )

    stats = {
        "total": Item.query.count(),
        "available": Item.query.filter_by(status=ItemStatus.AVAILABLE).count(),
        "pending": len(pending_claims),
        "returned": Item.query.filter_by(status=ItemStatus.CLAIMED).count(),
    }

    return render_template(
        "admin/dashboard.html",
        pending_claims=pending_claims,
        pagination=pagination,
        items=pagination.items,
        stats=stats,
        admin_email=session.get("user_email"),
    )


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Administrator session ended.", "info")
    return redirect(url_for("admin.login"))
