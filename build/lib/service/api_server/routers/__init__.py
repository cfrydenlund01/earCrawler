from __future__ import annotations

from fastapi import APIRouter

from . import entities, health, lineage, search, sparql


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(entities.router)
    router.include_router(search.router)
    router.include_router(sparql.router)
    router.include_router(lineage.router)
    return router
