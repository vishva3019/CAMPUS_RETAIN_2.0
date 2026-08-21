"""WSGI entry point.

Vercel's Python runtime and any standard WSGI server (gunicorn, waitress) look
for a module-level callable named ``app``. Keeping it in its own tiny module
means importing the package for tests or CLI use does not construct an
application as a side effect.

Local development:
    flask --app wsgi run --debug
Production:
    gunicorn wsgi:app
"""

from __future__ import annotations

from app import create_app

app = create_app()


if __name__ == "__main__":
    # Debug mode is driven by FLASK_ENV, so this never enables the debugger in
    # production the way the old `app.run(debug=True)` would have.
    app.run()
