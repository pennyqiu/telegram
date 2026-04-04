from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_webhook_url: str
    mini_app_url: str

    # 数据库 / 缓存
    database_url: str
    redis_url: str

    # 订阅配置
    grace_period_days: int = 3
    expiry_reminder_days: int = 3
    admin_telegram_ids: str = ""
    internal_api_key: str

    # ── 微信支付 ────────────────────────────────────────────────
    wechat_appid: str = ""              # 微信公众号/小程序/开放平台 AppID
    wechat_mchid: str = ""              # 商户号
    wechat_apiv3_key: str = ""          # API v3 密钥（32位）
    wechat_private_key: str = ""        # 商户私钥（PEM 字符串，\n 转义）
    wechat_cert_serial_no: str = ""     # 商户证书序列号
    wechat_notify_url: str = ""         # 微信回调地址

    # ── 支付宝 ──────────────────────────────────────────────────
    alipay_app_id: str = ""             # 支付宝开放平台 AppID
    alipay_private_key: str = ""        # 应用私钥（RSA2，PEM）
    alipay_public_key: str = ""         # 支付宝公钥（用于验签）
    alipay_notify_url: str = ""         # 支付宝回调地址

    @property
    def admin_ids(self) -> list[int]:
        return [int(i) for i in self.admin_telegram_ids.split(",") if i.strip()]

    @property
    def wechat_enabled(self) -> bool:
        return bool(self.wechat_appid and self.wechat_mchid and self.wechat_apiv3_key)

    @property
    def alipay_enabled(self) -> bool:
        return bool(self.alipay_app_id and self.alipay_private_key and self.alipay_public_key)


settings = Settings()
