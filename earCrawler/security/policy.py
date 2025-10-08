from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Iterable, List, Dict, Set, Tuple

import click
import sys
import time

from earCrawler.audit import ledger
from earCrawler.telemetry import redaction

POLICY_PATH = os.path.join("security", "policy.yml")


class PolicyError(Exception):
    """Raised when policy denies access or is misconfigured."""


@dataclass
class Policy:
    roles: Dict[str, List[str]]
    commands: Dict[str, List[str]]
    overrides: Dict[str, Dict[str, List[str] | List[str]]] = field(default_factory=dict)

    def roles_for_user(self, user: str) -> Set[str]:
        base: Set[str] = set()
        if user in self.overrides and self.overrides[user].get("roles"):
            base.update(self.overrides[user]["roles"])
        elif "default" in self.overrides and self.overrides["default"].get("roles"):
            base.update(self.overrides["default"]["roles"])
        return base

    def required_roles_for(self, command: str) -> List[str]:
        return self.commands.get(command, [])

    def check_access(self, user: str, command: str, required: Iterable[str] | None = None) -> Tuple[bool, str]:
        roles = self.roles_for_user(user)
        needed = list(required) if required else self.required_roles_for(command)
        if not needed:
            return False, f"command '{command}' is not permitted"
        # explicit deny
        deny = set(self.overrides.get(user, {}).get("deny", []))
        if command in deny:
            return False, f"{user} is explicitly denied '{command}'"
        if any(r == "admin" for r in roles):
            return True, ""
        if roles.intersection(needed):
            return True, ""
        return False, f"command '{command}' requires role(s): {', '.join(needed)}"


def load_policy(path: str | None = None) -> Policy:
    pol_path = path or os.environ.get("EARCTL_POLICY_PATH") or POLICY_PATH
    with open(pol_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Policy(
        roles=data.get("roles", {}),
        commands=data.get("commands", {}),
        overrides=data.get("overrides", {}),
    )


def require_role(*roles: str) -> Callable:
    """Decorator to declare required roles for a CLI command."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapped(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapped, "required_roles", list(roles))
        return wrapped

    return decorator


def enforce(fn: Callable) -> Callable:
    """Decorator enforcing policy and emitting audit events."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        parts = ctx.command_path.split()
        cmd = None
        if parts:
            for part in parts[1:]:
                if part == "-m":
                    continue
                if any(sep in part for sep in (".", "/", "\\")):
                    continue
                cmd = part
                break
            if cmd is None:
                cmd = parts[-1]
        if not cmd and ctx.command is not None:
            cmd = ctx.command.name or ""

        # For nested commands Click will report the leaf command name in
        # ``cmd`` (e.g. ``start``) which may not have a direct policy entry.
        # Fall back to the nearest parent command that has a policy rule so
        # that groups like ``api`` still enforce their access controls.
        pol = load_policy()
        if cmd and cmd not in pol.commands:
            parent_ctx = ctx.parent
            while parent_ctx is not None:
                parent_name = parent_ctx.command.name if parent_ctx.command else ""
                if parent_name and parent_name in pol.commands:
                    cmd = parent_name
                    break
                parent_ctx = parent_ctx.parent
        from . import identity
        ident = identity.whoami()
        required = getattr(fn, "required_roles", None)
        if required is None and ctx.command is not None:
            required = getattr(ctx.command.callback, "required_roles", None)
        allowed, msg = pol.check_access(ident["user"], cmd, required)
        args_sanitized = str(redaction.redact(" ".join(sys.argv[1:])))
        if not allowed:
            ledger.append_event("denied", ident["user"], ident["roles"], cmd, args_sanitized, 1, 0)
            raise click.ClickException(msg)
        start = time.time()
        try:
            rv = fn(*args, **kwargs)
            ledger.append_event("command", ident["user"], ident["roles"], cmd, args_sanitized, 0, int((time.time()-start)*1000))
            return rv
        except Exception:
            ledger.append_event("command", ident["user"], ident["roles"], cmd, args_sanitized, 1, int((time.time()-start)*1000))
            raise

    return wrapper
