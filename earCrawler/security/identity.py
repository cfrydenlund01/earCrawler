from __future__ import annotations

import getpass
import os
from typing import Dict

from . import cred_store
from .policy import allow_unsafe_env_overrides, load_policy


def whoami() -> Dict[str, object]:
    """Resolve current identity with roles."""
    env_user = os.getenv("EARCTL_USER")
    user = env_user if env_user and allow_unsafe_env_overrides() else getpass.getuser()
    token = os.environ.get("EARCTL_AUTH_TOKEN") or cred_store.get_secret(
        "EARCTL_AUTH_TOKEN"
    )
    pol = load_policy()
    roles = sorted(pol.roles_for_user(user))
    return {"user": user, "roles": roles, "via_token": bool(token)}
