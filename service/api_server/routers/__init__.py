from __future__ import annotations

from fastapi import APIRouter

from . import entities, health, lineage, rag, search, sparql


def build_router(*, enable_search: bool = False) -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(entities.router)
    if enable_search:
        router.include_router(search.router)
    router.include_router(sparql.router)
    router.include_router(lineage.router)
    router.include_router(rag.router)
    return router
