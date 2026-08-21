"""The browsable register of found items."""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from app.models import Item, ItemStatus
from app.security import current_user_email, is_admin, login_required

bp = Blueprint("items", __name__)


@bp.route("/")
@login_required
def index():
    """Paginated, server-filtered list of found items.

    Both the pagination and the filtering are new. Previously every row was
    loaded and rendered on one page, with search implemented in JavaScript by
    hiding cards that were already in the DOM -- so the browser downloaded the
    entire register (including every base64-encoded photo) just to show four
    matches.
    """
    query_text = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", type=int, default=1)

    query = Item.query

    if query_text:
        # Match the name or the place it was found, which is how people
        # actually search ("library", "black wallet").
        pattern = f"%{query_text}%"
        query = query.filter(
            Item.name.ilike(pattern) | Item.location.ilike(pattern)
        )

    if category and category in current_app.config["ITEM_CATEGORIES"]:
        query = query.filter(Item.category == category)

    if status in ItemStatus.ALL:
        query = query.filter(Item.status == status)

    pagination = query.order_by(Item.date_found.desc()).paginate(
        page=max(1, page),
        per_page=current_app.config["ITEMS_PER_PAGE"],
        error_out=False,
    )

    return render_template(
        "items/index.html",
        pagination=pagination,
        items=pagination.items,
        categories=current_app.config["ITEM_CATEGORIES"],
        statuses=ItemStatus.ALL,
        filters={"q": query_text, "category": category, "status": status},
        user_email=current_user_email(),
        viewer_is_admin=is_admin(),
    )
