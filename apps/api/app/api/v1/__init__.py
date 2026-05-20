from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.market import router as market_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.virtual import router as virtual_router
from app.api.v1.watchlist import router as watchlist_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(market_router)
router.include_router(watchlist_router)
router.include_router(virtual_router)
router.include_router(notifications_router)
router.include_router(analysis_router)
