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

    # 访问统计埋点 ingest 防滥用密钥(可选 · 空=不校验)· Next 中间件 beacon 带 x-track-secret。
    track_ingest_secret: str = ""

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

    # 支付 · Bcon(旧网关 · 保留作回归参照 · order/payment 已不 import · Phase 2a)
    # ⚠ 敏感:bcon_api_key 只从 env 读 · 绝不进 git/前端/DB/日志 · 空 = 支付未启用。
    bcon_api_key: str = ""
    bcon_api_base: str = "https://external-api.bcon.global"
    bcon_timeout_seconds: float = 15.0

    # 阿里云 OSS · 周报素材原始文件归档(第三刀-B · prefix report-materials/ · 桶 lifecycle 7 天)
    # ⚠ 敏感:oss_access_key_id/secret 只从 env 读 · 绝不进 git/前端/DB/日志(脱敏)· 空 = 上传未启用。
    # ★凭证现在 VPS /etc/midas/backup.env,需 Hans 复制到 app 容器 env(/opt/midas/.env)。
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    # 内网端点(api/worker 容器在阿里云香港可用 · 免公网流量费)· bucket 香港 region
    oss_endpoint: str = "oss-cn-hongkong-internal.aliyuncs.com"
    oss_bucket: str = "midas-backup-hk"

    # 支付 · OxaPay(现行网关 · 会员订阅收款 · USDT 多链托管页 · Phase 2a)
    # ⚠ 敏感:oxapay_merchant_api_key 只从 env 读 · 绝不进 git/前端/DB/日志 ·
    #    既是建单/查单凭证,又是回调 HMAC-SHA512 验签密钥 · 空 = 支付未启用(回调全拒)。
    oxapay_merchant_api_key: str = ""
    oxapay_api_base: str = "https://api.oxapay.com"
    oxapay_timeout_seconds: float = 20.0
    # 沙盒开关:True = 建单走 OxaPay 测试网(不收真钱,验回调全链路);上真钱前设 False。
    oxapay_sandbox: bool = False
    # 托管收款页有效期(分钟)· 超时未付订单作废。
    oxapay_lifetime_minutes: int = 60
    # 少付容差(百分比 · 0-60)· 实付 ≥ 应付 ×(1 - coverage/100)即判付清 ·
    # 吸收链上手续费(用户付满额,手续费导致实到略少不该卡单)· 默认 5%(覆盖手续费≤0.245 的链,
    # 含 0.2 的高费链 + 余量)· 按百分比对 4.9/9.9/19.9 三档自动适配 · 商户自吸收不转嫁用户。
    oxapay_under_paid_coverage: float = 5.0

    # 支付工单 / 退款申请(support 模块)· 工单存 DB + Resend 邮件通知客服 · 图走附件不落盘。
    # ⚠ Resend API key 复用 email.py 的 env RESEND_API_KEY(不在此重复配)。
    # 发件必须用已验证域名 support@midastrade.asia(onboarding@resend.dev 测试域名发不到 Gmail)。
    support_email_to: str = "hans.pan002@gmail.com"            # 客服收件箱(env SUPPORT_EMAIL_TO)
    support_email_from: str = "Midas Support <support@midastrade.asia>"  # env SUPPORT_EMAIL_FROM
    support_max_images: int = 3       # 单工单图片张数上限
    support_max_image_mb: int = 5     # 单张图片大小上限(MB)


settings = Settings()
