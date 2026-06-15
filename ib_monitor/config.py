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
class CCRollConfig:
    """Covered Call 展期触发配置"""
    # 各标的 CC 展期触发 Delta 阈值（key=symbol, value=delta阈值）
    # 未在此列出的标的使用 default_delta
    default_delta: float
    symbol_delta: dict        # e.g. {"NVDA": 0.35}
    profit_take_pct: float    # 止盈比例：盈利超过初始权利金此比例时平仓
    shares_per_contract: int  # 每张合约对应股数（标准美股期权=100）


@dataclass
class PositionTargets:
    """标的凑整目标与积攒计划配置"""
    # 各标的需凑整到的目标股数（达到后可开 CC）
    cc_targets: dict          # e.g. {"MSFT": 100, "NVDA": 100, ...}
    # SPYM 积攒目标（达到后触发 VOO Swap 提醒）
    spym_target: int
    # SPYM -> VOO 置换比例
    spym_to_voo_ratio: float  # 844股SPYM ≈ 110股VOO


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

CC_ROLL = CCRollConfig(
    default_delta=float(os.getenv("CC_ROLL_DEFAULT_DELTA", "0.40")),
    symbol_delta={
        # NVDA 更激进，Delta 0.35 就触发展期
        "NVDA": float(os.getenv("CC_ROLL_NVDA_DELTA", "0.35")),
    },
    profit_take_pct=float(os.getenv("CC_PROFIT_TAKE_PCT", "0.50")),
    shares_per_contract=100,
)

POSITION_TARGETS = PositionTargets(
    cc_targets={
        "MSFT": 100, "NVDA": 100, "TSM": 100,
        "GOOG": 100, "META": 100, "QQQM": 100,
    },
    spym_target=int(os.getenv("SPYM_TARGET", "844")),
    spym_to_voo_ratio=float(os.getenv("SPYM_TO_VOO_RATIO", "0.1303")),  # 844/110 ≈ 7.67股SPYM换1股VOO
)

SCHEDULE = ScheduleConfig(
    check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
    daily_report_hour=int(os.getenv("DAILY_REPORT_HOUR", "8")),
    daily_report_minute=int(os.getenv("DAILY_REPORT_MINUTE", "30")),
)
