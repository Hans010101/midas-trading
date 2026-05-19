"""数据源业务异常树。

所有适配器(AKShare / yfinance / ccxt)失败时**必须**抛这里定义的异常之一,
绝不允许悄悄返回空列表。

异常的 __str__ 会把 market / symbol / upstream 信息拼进来,
方便 Task 6 之后接告警时直接 grep stdout 抓关键字。
"""

from __future__ import annotations


class DataSourceError(Exception):
    """所有数据源异常的根类。携带 market / symbol / upstream 三段上下文。"""

    def __init__(
        self,
        message: str,
        *,
        market: str | None = None,
        symbol: str | None = None,
        upstream: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.market = market
        self.symbol = symbol
        self.upstream = upstream

    def __str__(self) -> str:
        ctx_parts = [
            f"{k}={v}"
            for k, v in (
                ("market", self.market),
                ("symbol", self.symbol),
                ("upstream", self.upstream),
            )
            if v
        ]
        ctx = " | ".join(ctx_parts)
        return f"{self.message}{(' [' + ctx + ']') if ctx else ''}"


class UpstreamUnavailableError(DataSourceError):
    """上游 SDK / HTTP 不可达:超时、连接拒绝、5xx、DNS 失败等。

    通常意味着可重试。retry 装饰器会自动捕获并退避重试。
    """


class RateLimitError(UpstreamUnavailableError):
    """被上游限流(429 / Binance -1003 / AKShare 隐式封禁 等)。

    继承自 UpstreamUnavailableError,但在告警和退避策略上要单独处理:
    退避时间应明显长于普通超时(避免火上浇油)。
    """


class SymbolNotFoundError(DataSourceError):
    """标的代码上游不存在 / 已退市 / 不支持的市场。

    这是终态错误,**不要重试**。直接抛给调用方,由 service / 路由层
    决定是返回 404 还是从 symbol_meta 标记 is_active=False。
    """


class DataFormatError(DataSourceError):
    """上游返回了数据,但字段缺失、类型错位、OHLC 不自洽,无法映射到 Kline schema。

    这是终态错误,**不要重试**。意味着上游协议变了,需要修适配器。
    """
