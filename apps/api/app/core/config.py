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

    # Telegram 统一 bot(0024 v2 · M1-G G1)· 与旧 per-user bot 并存,G2 才切换派发。
    # ⚠ tg_bot_token 敏感:只从 env 读 · 绝不进 git/前端/DB · 空 = 统一 bot 未启用。
    tg_bot_token: str = ""
    # bot 用户名(拼 t.me deep link)· D9 待定 · 可空(前端 G3 补)。
    tg_bot_username: str = ""
    # 公网 API base · 拼 webhook URL · prod = https://api.midastrade.asia · 非 secret。
    public_api_base_url: str = "http://localhost:8000"
    # 公网 Web base · 拼 bot K 线深链(DP14)· prod = https://midastrade.asia · 非 secret。
    public_web_base_url: str = "http://localhost:3000"
    # /start 一次性绑定 token TTL(秒)。
    tg_bind_token_ttl_seconds: int = 600
    # webhook secret 不单独配:由 secret_key 派生(见 telegram_bind.webhook_secret)。

    # 飞书(Lark)企业自建应用 · ADR 0032 多通道 · 阶段二(通知推送)。
    # ⚠ 敏感:feishu_app_secret / feishu_*_token / encrypt_key 只从 env 读 ·
    #    绝不进 git/前端/DB · 任一为空 = 飞书未启用(dispatcher 静默跳过)。
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # 事件订阅验签:Verification Token(配了才校验)· Encrypt Key(配了才解密事件)。
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    # 飞书 open API base · 国内租户 open.feishu.cn;海外租户改 open.larksuite.com。
    feishu_api_base: str = "https://open.feishu.cn"

    # AI 决策卡 · 0012 ADR · M1 第二波
    llm_provider: str = "deepseek"           # litellm 命名(deepseek / openai / claude 等)
    llm_model: str = "deepseek/deepseek-chat"
    deepseek_api_key: str = ""               # 产品负责人提供 · 空字符串时强制 mock 模式
    llm_monthly_budget_cny: float = 200.0    # 软上限 · ai_usage_log 累计到 80% 邮件告警
    llm_mock_mode: bool = False              # 显式 True 强制 mock(即使有 key)· 测试用
    llm_max_tokens: int = 1024               # 单次响应硬上限
    llm_timeout_seconds: float = 30.0


settings = Settings()
