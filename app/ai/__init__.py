"""Proxy package for app.ai referencing canonical ai package."""

from __future__ import annotations

import sys
import ai

sys.modules["app.ai"] = ai
from ai import *  # noqa: F401, F403
