from __future__ import annotations

import getpass
import os
from typing import Dict

from . import cred_store
from .policy import load_policy


def whoami() -> Dict[str, object]:
    """Resolve current identity with roles."""
    user = os.getenv("EARCTL_USER") or getpass.getuser()
    token = os.environ.get("EARCTL_AUTH_TOKEN") or cred_store.get_secret("EARCTL_AUTH_TOKEN")
    pol = load_policy()
    roles = sorted(pol.roles_for_user(user))
    return {"user": user, "roles": roles, "via_token": bool(token)}
