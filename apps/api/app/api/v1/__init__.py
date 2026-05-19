from fastapi import APIRouter

from app.api.v1.market import router as market_router

router = APIRouter()
router.include_router(market_router)

# TODO(M0): 后续子路由(watchlist / virtual / notifications)随 Task 4-6 挂载到这里。
