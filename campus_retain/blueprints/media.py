"""Item photos. The bucket is private: every request is checked against the viewer's
college, then served (local/memory) or redirected to a short-lived signed R2 URL."""
from flask import Blueprint, Response, abort, current_app, g, redirect, url_for

from ..models import Item, ItemImage, ItemStatus
from ..security import college_member_required, permission_required, tenant_query
from ..services.storage import StorageError, get_storage

bp = Blueprint("media", __name__, url_prefix="/media")


@bp.route("/item-image/<int:image_id>")
@college_member_required
@permission_required("items.view")
def item_image(image_id):
    image = (tenant_query(ItemImage).filter(ItemImage.id == image_id)
             .join(Item, Item.id == ItemImage.item_id).first())
    if image is None:
        abort(404)
    item = image.item
    if item.status == ItemStatus.REMOVED and not g.user.has_permission("items.manage"):
        abort(404)
    store = get_storage()
    if store is None:
        abort(404)
    ttl = current_app.config["MEDIA_URL_TTL_SECONDS"]
    signed = store.signed_url(image.storage_key)
    if signed:
        resp = redirect(signed, code=302)
    else:
        try:
            resp = Response(store.get(image.storage_key), mimetype=image.content_type)
        except StorageError:
            abort(404)
    # Private: the URL is only useful to signed-in members of this college.
    resp.headers["Cache-Control"] = f"private, max-age={max(ttl - 60, 0)}"
    return resp


def photo_urls(item):
    """URLs for an item's photos, for templates. Falls back to the 2.0 inline photo."""
    if item.images:
        return [url_for("media.item_image", image_id=img.id) for img in item.images]
    if item.image_data:
        return [item.image_data]
    return []


def photo_url(item):
    urls = photo_urls(item)
    return urls[0] if urls else url_for("static", filename="no-image.svg")
