from app.core.database import Base  # noqa: F401
from app.models.academy_exam_award import AcademyExamAward  # noqa: F401
from app.models.academy_exam_result import AcademyExamResult  # noqa: F401
from app.models.academy_progress import AcademyProgress  # noqa: F401
from app.models.ai_analysis_memory import AIAnalysisMemory  # noqa: F401
from app.models.ai_usage import AIUsageLog  # noqa: F401
from app.models.backtest_run import BacktestRun  # noqa: F401
from app.models.bot_order_preset import BotOrderPreset  # noqa: F401
from app.models.daily_crawler_stat import DailyCrawlerStat  # noqa: F401
from app.models.daily_referrer_stat import DailyReferrerStat  # noqa: F401
from app.models.daily_source_stat import DailySourceStat  # noqa: F401
from app.models.daily_visit_stat import DailyVisitStat  # noqa: F401
from app.models.econ_event import EconEvent  # noqa: F401
from app.models.hk_board_lot import HkBoardLot  # noqa: F401
from app.models.hk_sector import HkSector  # noqa: F401
from app.models.intelligent_review import IntelligentReview  # noqa: F401
from app.models.market_report import MarketReport  # noqa: F401
from app.models.notification import NotificationConfig  # noqa: F401
from app.models.payment_order import PaymentOrder  # noqa: F401
from app.models.perp import (  # noqa: F401
    MarginMode,
    PerpAction,
    PerpCloseReason,
    PerpSide,
    VirtualPerpOrder,
    VirtualPerpPosition,
)
from app.models.platform_dispatch import PlatformDispatch  # noqa: F401
from app.models.report_material import ReportMaterial  # noqa: F401
from app.models.session import Session as AuthSession  # noqa: F401
from app.models.support_ticket import SupportTicket  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.verification_token import TokenPurpose, VerificationToken  # noqa: F401
from app.models.virtual import (  # noqa: F401
    Currency,
    OrderSide,
    OrderStatus,
    OrderType,
    SnapshotTrigger,
    VirtualAccount,
    VirtualEquitySnapshot,
    VirtualOrder,
    VirtualPosition,
)
from app.models.watchlist import WatchlistItem  # noqa: F401
from app.models.weekly_dispatch import WeeklyDispatch  # noqa: F401
from app.models.x_tweet import XTweet  # noqa: F401
