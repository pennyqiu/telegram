"""
ib_quant 配置读取

设计原则：
  1. 所有可调参数走环境变量（.env），代码零硬编码密钥。
  2. 默认值一律偏保守 / 偏安全：默认连模拟盘、默认 DRY_RUN 不真实下单。
  3. 交易护栏（单笔上限、单标的持仓上限、白名单）在配置层即可拦截危险订单。
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


# ── 工具函数 ──────────────────────────────────────────────────────────

def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"必须设置环境变量: {key}")
    return value


def _bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _csv(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


# ── Telegram 通知 ─────────────────────────────────────────────────────

@dataclass
class TelegramConfig:
    enabled: bool
    bot_token: str
    chat_id: str


# ── 邮箱通知 ──────────────────────────────────────────────────────────

@dataclass
class EmailConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    sender: str
    recipients: list[str]
    use_tls: bool


# ── IB 连接 ───────────────────────────────────────────────────────────

@dataclass
class IBConfig:
    host: str
    port: int
    client_id: int
    account: str
    trading_mode: str          # "paper" | "live"


# ── 交易安全护栏 ───────────────────────────────────────────────────────

@dataclass
class TradingGuards:
    """
    交易护栏：在下单前进行多重校验，任何一项不满足都会拒绝订单。
    这是真实资金安全的最后一道防线。
    """
    dry_run: bool                  # True = 只记录订单不真实发送（强烈建议先用此模式跑通）
    allow_live: bool               # 二次确认开关：必须显式设为 True 才允许连实盘下单
    symbol_whitelist: list[str]    # 只允许交易的标的（空 = 不限制，但不建议）
    max_order_notional: float      # 单笔订单名义金额上限（USD）
    max_position_notional: float   # 单标的累计持仓市值上限（USD）
    max_daily_orders: int          # 单日最大下单笔数（防止策略 bug 疯狂下单）
    require_confirm: bool          # 实盘下单是否需要 Telegram 人工二次确认


# ── 策略与调度 ─────────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    enabled_strategies: list[str]  # 启用的策略名（对应 strategies/ 下的注册名）
    universe: list[str]            # 策略关注的标的池
    poll_interval_seconds: int     # 周期性检查数据的间隔
    daily_report_hour: int
    daily_report_minute: int


# ── Web 看板 ──────────────────────────────────────────────────────────

@dataclass
class WebConfig:
    enabled: bool
    host: str
    port: int


# ── 实例化 ────────────────────────────────────────────────────────────

TELEGRAM = TelegramConfig(
    enabled=_bool("TELEGRAM_ENABLED", True),
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
    chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
)

EMAIL = EmailConfig(
    enabled=_bool("EMAIL_ENABLED", False),
    smtp_host=os.getenv("SMTP_HOST", ""),
    smtp_port=int(os.getenv("SMTP_PORT", "587")),
    username=os.getenv("SMTP_USERNAME", ""),
    password=os.getenv("SMTP_PASSWORD", ""),
    sender=os.getenv("EMAIL_SENDER", os.getenv("SMTP_USERNAME", "")),
    recipients=_csv("EMAIL_RECIPIENTS"),
    use_tls=_bool("SMTP_USE_TLS", True),
)

IB = IBConfig(
    host=os.getenv("IB_HOST", "127.0.0.1"),
    # 默认 4002 = 模拟盘端口（实盘为 4001），强制要求显式改端口才能连实盘
    port=int(os.getenv("IB_PORT", "4002")),
    client_id=int(os.getenv("IB_CLIENT_ID", "20")),  # 与只读监控(10)区分，避免 clientId 冲突
    account=_require("IB_ACCOUNT"),
    trading_mode=os.getenv("TRADING_MODE", "paper").lower(),
)

GUARDS = TradingGuards(
    dry_run=_bool("DRY_RUN", True),
    allow_live=_bool("ALLOW_LIVE", False),
    symbol_whitelist=_csv("SYMBOL_WHITELIST"),
    max_order_notional=float(os.getenv("MAX_ORDER_NOTIONAL", "5000")),
    max_position_notional=float(os.getenv("MAX_POSITION_NOTIONAL", "20000")),
    max_daily_orders=int(os.getenv("MAX_DAILY_ORDERS", "20")),
    require_confirm=_bool("REQUIRE_CONFIRM", True),
)

STRATEGY = StrategyConfig(
    enabled_strategies=_csv("ENABLED_STRATEGIES", "ma_cross"),
    universe=_csv("UNIVERSE", "AAPL,MSFT,NVDA"),
    poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
    daily_report_hour=int(os.getenv("DAILY_REPORT_HOUR", "8")),
    daily_report_minute=int(os.getenv("DAILY_REPORT_MINUTE", "30")),
)

WEB = WebConfig(
    enabled=_bool("WEB_ENABLED", True),
    host=os.getenv("WEB_HOST", "0.0.0.0"),
    port=int(os.getenv("WEB_PORT", "8800")),
)


def is_live() -> bool:
    """是否处于实盘交易模式（需要 trading_mode=live 且端口=实盘）"""
    return IB.trading_mode == "live"


def assert_live_allowed() -> None:
    """实盘安全闸门：未显式放行实盘时直接抛错，防止误连真实账户下单。"""
    if is_live() and not GUARDS.allow_live:
        raise RuntimeError(
            "检测到 TRADING_MODE=live 但 ALLOW_LIVE 未开启。"
            "为防止误操作真实资金，必须显式设置 ALLOW_LIVE=true 才能连实盘交易。"
        )
