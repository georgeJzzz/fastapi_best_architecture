from fastapi import APIRouter

from backend.app.admin.api.v1.auth import router as auth_router
from backend.app.admin.api.v1.log import router as log_router
from backend.app.admin.api.v1.monitor import router as monitor_router
from backend.app.admin.api.v1.sys import router as sys_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(sys_router)
router.include_router(log_router)
router.include_router(monitor_router)
