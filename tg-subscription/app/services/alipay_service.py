"""
支付宝服务封装

依赖：alipay-sdk-python-new
文档：https://opendocs.alipay.com/open/270/105898

商户需要：
  - 支付宝 AppID
  - 应用私钥（RSA2，PEM 格式）
  - 支付宝公钥（从开放平台获取，用于验签）
"""

from __future__ import annotations
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

_alipay = None


def _get_alipay():
    global _alipay
    if _alipay is None:
        from alipay import AliPay
        _alipay = AliPay(
            appid=settings.alipay_app_id,
            app_notify_url=settings.alipay_notify_url,
            app_private_key_string=settings.alipay_private_key,
            alipay_public_key_string=settings.alipay_public_key,
            sign_type="RSA2",
            debug=False,
        )
    return _alipay


def create_page_pay_url(
    out_trade_no: str,
    amount_fen: int,
    subject: str,
    return_url: str,
) -> str:
    """
    创建支付宝电脑/H5 支付 URL（alipay.trade.page.pay）。
    amount_fen: 人民币金额，单位分
    return_url: 支付完成后跳回的前端地址（非通知地址）
    """
    alipay = _get_alipay()
    total_amount = f"{amount_fen / 100:.2f}"
    order_string = alipay.api_alipay_trade_page_pay(
        out_trade_no=out_trade_no,
        total_amount=total_amount,
        subject=subject,
        return_url=return_url,
    )
    return f"https://openapi.alipay.com/gateway.do?{order_string}"


def create_wap_pay_url(
    out_trade_no: str,
    amount_fen: int,
    subject: str,
    return_url: str,
) -> str:
    """
    创建支付宝 WAP（手机网页）支付 URL（alipay.trade.wap.pay）。
    更适合手机端 Telegram Mini App 内跳转。
    """
    alipay = _get_alipay()
    total_amount = f"{amount_fen / 100:.2f}"
    order_string = alipay.api_alipay_trade_wap_pay(
        out_trade_no=out_trade_no,
        total_amount=total_amount,
        subject=subject,
        return_url=return_url,
    )
    return f"https://openapi.alipay.com/gateway.do?{order_string}"


def query_order(out_trade_no: str) -> dict:
    """查询支付宝订单状态"""
    alipay = _get_alipay()
    result = alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
    return result


def verify_notification(data: dict) -> bool:
    """验证支付宝异步通知签名，返回是否合法"""
    try:
        alipay = _get_alipay()
        sign = data.pop("sign", None)
        return alipay.verify(data, sign) if sign else False
    except Exception as e:
        logger.error("支付宝通知验签失败: %s", e)
        return False
