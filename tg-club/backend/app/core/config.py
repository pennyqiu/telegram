from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 数据库 / 缓存
    club_db_url: str
    redis_url: str

    # 管理后台 JWT 认证
    admin_jwt_secret: str
    admin_username: str
    admin_password: str

    # 管理后台 Web 地址（Bot 内联按钮跳转用）
    admin_web_url: str = "https://admin.yourdomain.com"

    # Telegram Bot（俱乐部查询 Bot）
    club_bot_token: str = ""
    club_bot_webhook_url: str = ""
    club_bot_webhook_secret: str = ""

    # 管理员 Telegram ID 列表（逗号分隔，如 "123456789,987654321"）
    admin_telegram_ids: str = ""

    # 对接订阅系统（唯一耦合点：HTTP 调用）
    subscription_service_url: str
    subscription_internal_api_key: str

    # Cloudflare R2 图片存储（可选）
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "club-assets"
    r2_public_url: str = ""

    @property
    def admin_telegram_ids_set(self) -> set[int]:
        """将逗号分隔的 ID 字符串解析为 set[int]"""
        if not self.admin_telegram_ids:
            return set()
        return {int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()}

    @property
    def bot_enabled(self) -> bool:
        return bool(self.club_bot_token and self.club_bot_webhook_url)


settings = Settings()
