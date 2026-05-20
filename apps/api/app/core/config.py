from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 应用
    app_name: str = "点金 Midas"
    debug: bool = False

    # 数据库
    database_url: str = "postgresql+asyncpg://midas:midas_dev@localhost:5432/midas"

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "default"
    clickhouse_user: str = "midas"
    clickhouse_password: str = "midas_dev"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # JWT(必填,无默认值,强制从 env 注入)
    secret_key: str
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"

    # AI 决策卡 · 0012 ADR · M1 第二波
    llm_provider: str = "deepseek"           # litellm 命名(deepseek / openai / claude 等)
    llm_model: str = "deepseek/deepseek-chat"
    deepseek_api_key: str = ""               # 产品负责人提供 · 空字符串时强制 mock 模式
    llm_monthly_budget_cny: float = 200.0    # 软上限 · ai_usage_log 累计到 80% 邮件告警
    llm_mock_mode: bool = False              # 显式 True 强制 mock(即使有 key)· 测试用
    llm_max_tokens: int = 1024               # 单次响应硬上限
    llm_timeout_seconds: float = 30.0


settings = Settings()
