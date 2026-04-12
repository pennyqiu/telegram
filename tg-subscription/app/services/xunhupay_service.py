"""
虎皮椒聚合支付服务封装（xunhupay.com）

适用场景：无营业执照的个人开发者，无需申请官方微信/支付宝商户账号。
虎皮椒已持有商户资质，开发者通过其 API 间接收款，T+1 到账至个人微信/支付宝。

注册地址：https://www.xunhupay.com
API 文档：https://www.xunhupay.com/doc.html

商户需要：
  - XUNHUPAY_APPID     : 虎皮椒应用 ID
  - XUNHUPAY_APPSECRET : 虎皮椒应用密钥

签名算法：md5(sorted_params + appsecret)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

_GATEWAY = "https://api.xunhupay.com/payment/do.html"
_QUERY_URL = "https://api.xunhupay.com/payment/query.html"


# ── 签名工具 ──────────────────────────────────────────────────────

def _sign(params: dict, secret: str) -> str:
    """虎皮椒签名：对非空参数按键名升序排列后拼接密钥做 MD5"""
    filtered = {k: v for k, v in params.items() if k != "sign" and v not in (None, "")}
    sorted_str = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))
    raw = sorted_str + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _post(url: str, params: dict) -> dict:
    """发起 POST 请求，返回解析后的 JSON"""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


# ── 创建支付订单 ──────────────────────────────────────────────────

def create_order(
    out_trade_no: str,
    amount_fen: int,
    subject: str,
    channel: str,           # "wechat" 或 "alipay"
    notify_url: str,
    return_url: str = "",
) -> dict:
    """
    创建虎皮椒支付订单。

    返回 dict：
      - code_url   : 付款二维码内容（微信扫码）
      - pay_url    : 支付宝 WAP 跳转 URL
      - out_trade_no
    """
    # 虎皮椒 type 参数：wechat = 微信扫码，alipay = 支付宝
    # 两者都返回 url 字段：微信为 weixin:// 二维码内容，支付宝为跳转 URL
    type_map = {"wechat": "wechat", "alipay": "alipay"}
    pay_type = type_map.get(channel, "wechat")

    params: dict = {
        "appid":        settings.xunhupay_appid,
        "out_trade_no": out_trade_no,
        "total_fee":    f"{amount_fen / 100:.2f}",
        "title":        subject,
        "time":         str(int(time.time())),
        "notify_url":   notify_url,
        "nonce_str":    uuid.uuid4().hex,
        "type":         pay_type,
    }
    if return_url:
        params["return_url"] = return_url

    params["hash"] = _sign(params, settings.xunhupay_appsecret)

    resp = _post(_GATEWAY, params)
    logger.debug("虎皮椒下单响应: %s", resp)

    if resp.get("errcode") != 0:
        raise RuntimeError(f"虎皮椒下单失败: {resp.get('errmsg')} (code={resp.get('errcode')})")

    url = resp.get("url", "")
    return {
        "out_trade_no": out_trade_no,
        "code_url":     url if channel == "wechat" else "",
        "pay_url":      url if channel == "alipay" else "",
    }


# ── 查询订单状态 ──────────────────────────────────────────────────

def query_order(out_trade_no: str) -> dict:
    """
    查询虎皮椒订单状态。
    返回 dict，trade_status == "TRADE_SUCCESS" 表示已支付。
    """
    params = {
        "appid":        settings.xunhupay_appid,
        "out_trade_no": out_trade_no,
        "time":         str(int(time.time())),
        "nonce_str":    uuid.uuid4().hex,
    }
    params["hash"] = _sign(params, settings.xunhupay_appsecret)

    resp = _post(_QUERY_URL, params)
    logger.debug("虎皮椒查单响应: %s", resp)

    if resp.get("errcode") != 0:
        raise RuntimeError(f"虎皮椒查单失败: {resp.get('errmsg')}")

    # 虎皮椒返回 status: "OD" 表示已支付
    paid = resp.get("status") == "OD"
    return {
        "trade_status":  "TRADE_SUCCESS" if paid else "WAIT_BUYER_PAY",
        "trade_no":      resp.get("transaction_id", ""),
        "out_trade_no":  out_trade_no,
        "raw":           resp,
    }


# ── 验证异步通知签名 ──────────────────────────────────────────────

def verify_notification(data: dict) -> bool:
    """
    验证虎皮椒异步通知签名。
    通知参数中包含 hash 字段，用同样算法重新计算后比对。
    """
    received_hash = data.get("hash", "")
    expected_hash = _sign(data, settings.xunhupay_appsecret)
    return received_hash == expected_hash


def extract_notification(data: dict) -> dict | None:
    """
    解析通知数据，返回标准化字段。
    失败返回 None。
    """
    if not verify_notification(data):
        logger.warning("虎皮椒通知签名验证失败")
        return None

    paid = data.get("status") == "OD"
    return {
        "out_trade_no":  data.get("out_trade_no", ""),
        "trade_no":      data.get("transaction_id", ""),
        "trade_status":  "TRADE_SUCCESS" if paid else "WAIT_BUYER_PAY",
        "channel":       "wechat" if data.get("type") == "wechat" else "alipay",
    }
