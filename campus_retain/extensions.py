from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# No custom naming convention: constraint names stay PostgreSQL's defaults
# (user_pkey, user_email_key, claim_item_id_fkey, ...), which is what the
# existing 2.0 production database already uses.
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
