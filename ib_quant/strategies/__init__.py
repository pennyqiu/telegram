"""策略包：导入即触发各策略的 @register_strategy 注册。"""

from .base import Strategy, StrategyContext, build_strategies, register_strategy
from . import ma_cross  # noqa: F401  导入以触发注册

__all__ = [
    "Strategy", "StrategyContext", "build_strategies", "register_strategy",
]
