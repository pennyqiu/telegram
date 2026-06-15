"""
CC 开仓权利金持久化存储

用途：记录每张 Covered Call 开仓时收取的权利金，
      供 50% 止盈扫描器使用。

存储格式（JSON）：
  key:   "{SYMBOL}_{EXPIRY}_{STRIKE}_{RIGHT}"
         例：GOOG_20260620_390.0_C
  value: 开仓时收取的权利金（每股，美元）
         例：3.50
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.dirname(os.path.abspath(__file__))
_FILE = os.path.join(_DATA_DIR, "cc_premiums.json")


def _load() -> dict:
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    raw = {
        "_comment": "记录 Covered Call 开仓时的初始权利金，用于计算50%止盈触发点。",
        "_format": "key格式: SYMBOL_EXPIRY_STRIKE_C，value: 开仓时收取的权利金（每股，美元）",
        **data,
    }
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)


def make_key(symbol: str, expiry: str, strike: float, right: str) -> str:
    return f"{symbol}_{expiry}_{strike}_{right}"


def record_premium(symbol: str, expiry: str, strike: float, right: str, premium: float) -> None:
    """记录开仓权利金（手动调用或将来扩展为自动识别新开仓）"""
    data = _load()
    key = make_key(symbol, expiry, strike, right)
    data[key] = premium
    _save(data)
    logger.info("已记录 %s 开仓权利金 $%.2f", key, premium)


def get_premium(symbol: str, expiry: str, strike: float, right: str) -> float | None:
    """获取已记录的开仓权利金，未记录返回 None"""
    data = _load()
    key = make_key(symbol, expiry, strike, right)
    return data.get(key)


def remove_expired(active_keys: set[str]) -> None:
    """清理已到期/已平仓的合约记录，防止文件无限增长"""
    data = _load()
    cleaned = {k: v for k, v in data.items() if k in active_keys}
    if len(cleaned) < len(data):
        _save(cleaned)
        logger.info("清理了 %d 条已到期的权利金记录", len(data) - len(cleaned))


def list_all() -> dict:
    """列出所有记录（供调试用）"""
    return _load()
