from __future__ import annotations

from fastapi import APIRouter

from ..health import router as health_router

router = health_router
