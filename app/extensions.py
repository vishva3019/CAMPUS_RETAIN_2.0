"""Flask extension singletons.

Kept in their own module so blueprints can import ``db`` without importing the
application factory, which would create a circular import.
"""

from __future__ import annotations

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
