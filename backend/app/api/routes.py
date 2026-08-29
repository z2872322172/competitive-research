"""v1 API 聚合路由：按资源拆分的各 router 在此统一挂载。"""

from fastapi import APIRouter

from app.api import claims, competitors, reports, search, sources, system, tasks

router = APIRouter()
router.include_router(system.router)
router.include_router(tasks.router)
router.include_router(sources.router)
router.include_router(claims.router)
router.include_router(reports.router)
router.include_router(competitors.router)
router.include_router(search.router)
