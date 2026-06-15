import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TelegramConfig:
    bot_token: str
    alert_chat_id: str


@dataclass
class IBConfig:
    host: str
    port: int
    client_id: int
    account: str


@dataclass
class RiskThresholds:
    excess_liquidity_warn: float   # 剩余流动性预警线（占NLV比例）
    excess_liquidity_red: float    # 剩余流动性红线
    concentration_warn: float      # 单股集中度预警线
    concentration_red: float       # 单股集中度红线
    gamma_dte_threshold: int       # Gamma警戒DTE阈值（天）
    gamma_delta_min: float         # ATM判定：|delta|下限
    gamma_delta_max: float         # ATM判定：|delta|上限


@dataclass
class ScheduleConfig:
    check_interval_seconds: int
    daily_report_hour: int
    daily_report_minute: int


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"必须设置环境变量: {key}")
    return value


TELEGRAM = TelegramConfig(
    bot_token=_require("TELEGRAM_BOT_TOKEN"),
    alert_chat_id=_require("ALERT_CHAT_ID"),
)

IB = IBConfig(
    host=os.getenv("IB_HOST", "127.0.0.1"),
    port=int(os.getenv("IB_PORT", "4001")),
    client_id=int(os.getenv("IB_CLIENT_ID", "10")),
    account=_require("IB_ACCOUNT"),
)

RISK = RiskThresholds(
    excess_liquidity_warn=float(os.getenv("EXCESS_LIQUIDITY_WARN", "0.50")),
    excess_liquidity_red=float(os.getenv("EXCESS_LIQUIDITY_RED", "0.40")),
    concentration_warn=float(os.getenv("CONCENTRATION_WARN", "0.27")),
    concentration_red=float(os.getenv("CONCENTRATION_RED", "0.30")),
    gamma_dte_threshold=int(os.getenv("GAMMA_DTE_THRESHOLD", "14")),
    gamma_delta_min=float(os.getenv("GAMMA_DELTA_MIN", "0.30")),
    gamma_delta_max=float(os.getenv("GAMMA_DELTA_MAX", "0.70")),
)

SCHEDULE = ScheduleConfig(
    check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
    daily_report_hour=int(os.getenv("DAILY_REPORT_HOUR", "8")),
    daily_report_minute=int(os.getenv("DAILY_REPORT_MINUTE", "30")),
)
