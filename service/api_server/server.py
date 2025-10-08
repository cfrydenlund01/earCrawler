from __future__ import annotations

"""Uvicorn entrypoint for the read-only API."""

import uvicorn

from . import create_app
from .config import ApiSettings

_settings = ApiSettings.from_env()
app = create_app(_settings)


def main() -> None:  # pragma: no cover - convenience wrapper
    uvicorn.run(
        "service.api_server.server:app",
        host=_settings.host,
        port=_settings.port,
        factory=False,
        log_config=None,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
