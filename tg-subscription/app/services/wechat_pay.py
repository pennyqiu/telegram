"""
微信支付 v3 服务封装

依赖：wechatpayv3
文档：https://pay.weixin.qq.com/wiki/doc/apiv3/apis/chapter3_4_1.shtml

商户需要：
  - 微信支付商户号（mchid）
  - API v3 密钥（apiv3_key，32 位）
  - 商户私钥（merchant_private_key，PEM 格式）
  - 商户证书序列号（cert_serial_no）
"""

from __future__ import annotations
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

_pay = None


def _get_pay():
    global _pay
    if _pay is None:
        from wechatpay import WeChatPay, WeChatPayType
        _pay = WeChatPay(
            wechatpay_type=WeChatPayType.NATIVE,
            mchid=settings.wechat_mchid,
            private_key=settings.wechat_private_key,
            cert_serial_no=settings.wechat_cert_serial_no,
            appid=settings.wechat_appid,
            apiv3_key=settings.wechat_apiv3_key,
            notify_url=settings.wechat_notify_url,
        )
    return _pay


def create_native_order(out_trade_no: str, amount_fen: int, description: str) -> str:
    """
    创建 Native 扫码支付订单，返回 code_url（用于生成二维码）。
    amount_fen: 人民币金额，单位分（如 980 = ¥9.80）
    """
    pay = _get_pay()
    code, msg = pay.pay(
        description=description,
        out_trade_no=out_trade_no,
        amount={"total": amount_fen, "currency": "CNY"},
        pay_type=__import__("wechatpay").WeChatPayType.NATIVE,
    )
    if code != 200:
        raise RuntimeError(f"微信下单失败 [{code}]: {msg}")
    data = json.loads(msg) if isinstance(msg, str) else msg
    return data["code_url"]


def query_order(out_trade_no: str) -> dict:
    """查询订单状态，返回原始响应 dict"""
    pay = _get_pay()
    code, msg = pay.query(out_trade_no=out_trade_no)
    if code != 200:
        raise RuntimeError(f"微信查询失败 [{code}]: {msg}")
    return json.loads(msg) if isinstance(msg, str) else msg


def decode_notification(headers: dict, body: bytes) -> dict | None:
    """
    验证并解密微信支付通知，返回解密后的订单数据。
    失败返回 None。
    """
    try:
        pay = _get_pay()
        result = pay.callback(headers, body)
        return result
    except Exception as e:
        logger.error("微信支付通知解密失败: %s", e)
        return None
