"""Serves the React frontend (built into static/app by ``npm run build`` in frontend/).

Every /app/... path that is not a file returns index.html so client-side routes work on
reload. The onboarding screens (welcome, join, signin) are public; every other page needs
a signed-in user. The JSON API enforces permissions either way."""
import os

from flask import Blueprint, abort, current_app, g, redirect, request, send_from_directory, url_for

bp = Blueprint("spa", __name__)


def build_dir():
    return os.path.join(current_app.static_folder, "app")


def spa_available():
    return os.path.isfile(os.path.join(build_dir(), "index.html"))


PUBLIC_PAGES = ("welcome", "join", "signin")


def index_html():
    resp = send_from_directory(build_dir(), "index.html", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/app/")
@bp.route("/app/<path:path>")
def app_shell(path=""):
    if not spa_available():
        abort(404)
    page = path.strip("/").split("/", 1)[0]
    if page in PUBLIC_PAGES:
        if g.get("user") is not None:
            from .auth import _home_for
            return redirect(_home_for(g.user))
        return index_html()
    if g.get("user") is None and not path.startswith("assets/") and path != "sw.js":
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
    if path.startswith("assets/"):
        full = os.path.join(build_dir(), path)
        if os.path.isfile(full):
            resp = send_from_directory(build_dir(), path, max_age=31536000)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        abort(404)
    if path == "sw.js" and os.path.isfile(os.path.join(build_dir(), "sw.js")):
        resp = send_from_directory(build_dir(), "sw.js", max_age=0, mimetype="text/javascript")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Service-Worker-Allowed"] = "/app/"
        return resp
    return index_html()


@bp.route("/app")
def app_root():
    return redirect(url_for("spa.app_shell", **request.args))
