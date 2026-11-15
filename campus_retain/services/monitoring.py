"""Error monitoring with Sentry (Phase 7). Only runs when SENTRY_DSN is set.

No personal data is sent: no cookies, headers, request bodies, IP addresses or emails.
Events carry the user's numeric id and role so errors can be traced without identifying
anyone outside the database.
"""
SCRUB_HEADERS = {"cookie", "authorization", "x-csrftoken", "x-forwarded-for", "x-real-ip"}


def before_send(event, hint):
    request = event.get("request") or {}
    request.pop("cookies", None)
    request.pop("data", None)
    request.pop("query_string", None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in SCRUB_HEADERS:
            headers[key] = "[removed]"
    user = event.get("user") or {}
    event["user"] = {k: v for k, v in user.items() if k == "id"}
    return event


def init_sentry(app):
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(dsn=dsn, integrations=[FlaskIntegration()], send_default_pii=False,
                    environment=app.config.get("ENV_NAME"), traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0),
                    before_send=before_send)

    @app.before_request
    def _sentry_user():
        from flask import g
        user = g.get("user")
        if user is not None:
            sentry_sdk.set_user({"id": user.id})
            sentry_sdk.set_tag("role", user.role_name or "")
    return True
