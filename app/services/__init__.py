"""Service layer: outbound integrations and side effects.

Blueprints call into these modules rather than talking to SMTP, Twilio or
Cloudinary directly. That keeps request handlers readable and lets tests swap a
real integration for a fake without monkeypatching deep internals.
"""
