import { useEffect, useRef, useState } from "react";
import { useStore } from "../store/useStore";
import { useTelegram } from "../hooks/useTelegram";
import { api, Plan, ThirdPartyPayResult } from "../api/client";

// ── 支付渠道配置 ─────────────────────────────────────────────────
const CHANNELS = [
  { id: "stars",  icon: "⭐",  label: "Telegram Stars", color: "#f5a623" },
  { id: "wechat", icon: "💚",  label: "微信支付",        color: "#07c160" },
  { id: "alipay", icon: "💙",  label: "支付宝",          color: "#1677ff" },
] as const;

type Channel = (typeof CHANNELS)[number]["id"];

// ── 微信二维码弹窗 ────────────────────────────────────────────────
function WechatQrModal({
  order,
  qrcodeUrl,
  onClose,
  onPaid,
}: {
  order: ThirdPartyPayResult;
  qrcodeUrl: string;
  onClose: () => void;
  onPaid: () => void;
}) {
  const [status, setStatus] = useState<"pending" | "paid" | "expired" | "failed">("pending");
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    timerRef.current = setInterval(async () => {
      try {
        const res = await api.getPaymentStatus(order.out_trade_no);
        if (res.data.status === "paid") {
          clearInterval(timerRef.current);
          setStatus("paid");
          setTimeout(onPaid, 1200);
        } else if (res.data.status === "expired" || res.data.status === "failed") {
          clearInterval(timerRef.current);
          setStatus(res.data.status as "expired" | "failed");
        }
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(timerRef.current);
  }, [order.out_trade_no]);

  const overlay: React.CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,.6)",
    display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
  };
  const card: React.CSSProperties = {
    background: "#fff", borderRadius: 16, padding: 24,
    width: 280, textAlign: "center",
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        {status === "pending" && (
          <>
            <div style={{ fontSize: 18, fontWeight: "bold", marginBottom: 8 }}>
              💚 微信扫码支付
            </div>
            <div style={{ fontSize: 13, color: "#888", marginBottom: 12 }}>
              {order.amount_cny} · 15 分钟内有效
            </div>
            <img
              src={qrcodeUrl}
              alt="微信支付二维码"
              style={{ width: 200, height: 200, borderRadius: 8 }}
            />
            <div style={{ fontSize: 12, color: "#aaa", marginTop: 10 }}>
              使用微信 App 扫描上方二维码
            </div>
            <div style={{ fontSize: 11, color: "#bbb", marginTop: 6 }}>
              正在等待支付结果...
            </div>
          </>
        )}
        {status === "paid" && (
          <div style={{ fontSize: 32, padding: 20 }}>
            ✅<br />
            <span style={{ fontSize: 16, color: "#07c160" }}>支付成功！</span>
          </div>
        )}
        {(status === "expired" || status === "failed") && (
          <div style={{ fontSize: 14, color: "#f00", padding: 20 }}>
            ⚠️ {status === "expired" ? "二维码已过期，请重新发起支付" : "支付失败，请重试"}
          </div>
        )}
        <button
          onClick={onClose}
          style={{
            marginTop: 16, width: "100%", padding: "8px 0",
            border: "1px solid #ddd", borderRadius: 8,
            background: "#fff", cursor: "pointer", fontSize: 13,
          }}
        >
          关闭
        </button>
      </div>
    </div>
  );
}

// ── 支付渠道选择弹窗 ──────────────────────────────────────────────
function ChannelModal({
  plan,
  onClose,
  onStars,
  onThirdParty,
}: {
  plan: Plan;
  onClose: () => void;
  onStars: () => void;
  onThirdParty: (channel: "wechat" | "alipay") => void;
}) {
  const overlay: React.CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
    display: "flex", alignItems: "flex-end", justifyContent: "center", zIndex: 90,
  };
  const sheet: React.CSSProperties = {
    background: "#fff", borderRadius: "16px 16px 0 0",
    padding: "20px 20px 32px", width: "100%", maxWidth: 480,
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={sheet} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontWeight: "bold", fontSize: 16, marginBottom: 4 }}>
          选择支付方式
        </div>
        <div style={{ fontSize: 13, color: "#888", marginBottom: 20 }}>
          {plan.name}
        </div>

        {CHANNELS.map((ch) => {
          const disabled =
            (ch.id === "wechat" || ch.id === "alipay") && !plan.cny_price_fen;
          const amount =
            ch.id === "stars"
              ? `${plan.stars_price} Stars/月`
              : plan.cny_price_fen
              ? `¥${(plan.cny_price_fen / 100).toFixed(2)}/月`
              : "未开通";

          return (
            <button
              key={ch.id}
              disabled={disabled}
              onClick={() => {
                if (ch.id === "stars") onStars();
                else onThirdParty(ch.id as "wechat" | "alipay");
              }}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                width: "100%", padding: "14px 16px", marginBottom: 10,
                border: `1.5px solid ${disabled ? "#eee" : ch.color}`,
                borderRadius: 10, background: disabled ? "#fafafa" : "#fff",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.5 : 1,
              }}
            >
              <span style={{ fontSize: 15 }}>
                {ch.icon} {ch.label}
              </span>
              <span style={{ fontSize: 13, color: ch.color, fontWeight: "bold" }}>
                {amount}
              </span>
            </button>
          );
        })}

        <button
          onClick={onClose}
          style={{
            width: "100%", padding: "10px 0", marginTop: 4,
            border: "none", borderRadius: 8, background: "#f5f5f5",
            cursor: "pointer", fontSize: 14, color: "#666",
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────
export default function Plans() {
  const { plans, subscription, fetchPlans, fetchSubscription } = useStore();
  const { openInvoice, colorScheme, openLink } = useTelegram();

  const [channelModal, setChannelModal] = useState<Plan | null>(null);
  const [wechatOrder, setWechatOrder] = useState<ThirdPartyPayResult | null>(null);
  const [loading, setLoading] = useState<string>("");  // plan id being processed

  useEffect(() => { fetchPlans(); fetchSubscription(); }, []);

  // Stars 支付
  const handleStars = async (plan: Plan) => {
    setLoading(plan.id);
    try {
      const res = await api.createInvoice(plan.id);
      openInvoice(res.data.invoice_link, () => {
        fetchSubscription();
        setChannelModal(null);
      });
    } finally {
      setLoading("");
    }
  };

  // 微信/支付宝
  const handleThirdParty = async (plan: Plan, channel: "wechat" | "alipay") => {
    setLoading(plan.id);
    try {
      const res = await api.createThirdPartyPayment(plan.id, channel);
      setChannelModal(null);

      if (channel === "wechat") {
        setWechatOrder(res.data);
      } else {
        // 支付宝：在外部浏览器打开
        if (res.data.pay_url) {
          openLink(res.data.pay_url);
          // 打开后开始轮询（用户付完会回来）
          const poll = setInterval(async () => {
            const s = await api.getPaymentStatus(res.data.out_trade_no);
            if (s.data.status === "paid") {
              clearInterval(poll);
              fetchSubscription();
            } else if (s.data.status !== "pending") {
              clearInterval(poll);
            }
          }, 5000);
        }
      }
    } catch (e) {
      alert("发起支付失败，请重试");
    } finally {
      setLoading("");
    }
  };

  const isDark = colorScheme === "dark";
  const subBg = isDark ? "#1e3a5f" : "#e8f4fd";

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ marginBottom: 16 }}>选择订阅套餐</h2>

      {subscription && (
        <div style={{ background: subBg, borderRadius: 12, padding: 12, marginBottom: 16 }}>
          <strong>当前订阅：</strong>{subscription.plan_name}<br />
          <small>有效期至：{new Date(subscription.expires_at).toLocaleDateString()}</small>
        </div>
      )}

      {plans.map((plan) => {
        const isActive = subscription?.plan_id === plan.id;
        const isLoading = loading === plan.id;

        return (
          <div
            key={plan.id}
            style={{
              border: `1px solid ${isActive ? "#0088cc" : "#ddd"}`,
              borderRadius: 12, padding: 16, marginBottom: 12,
              background: isActive ? (isDark ? "#0d2a3d" : "#f0f8ff") : "transparent",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <strong style={{ fontSize: 16 }}>{plan.name}</strong>
              <div style={{ textAlign: "right", lineHeight: 1.4 }}>
                <div style={{ fontWeight: "bold", color: "#f5a623", fontSize: 13 }}>
                  ⭐ {plan.stars_price} Stars/月
                </div>
                {plan.cny_price_fen > 0 && (
                  <div style={{ fontSize: 12, color: "#888" }}>
                    ¥{(plan.cny_price_fen / 100).toFixed(2)}/月
                  </div>
                )}
              </div>
            </div>

            <ul style={{ margin: "8px 0", paddingLeft: 20, fontSize: 14 }}>
              {plan.features.map((f) => <li key={f}>{f}</li>)}
            </ul>

            {plan.trial_days > 0 && (
              <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
                新用户享 {plan.trial_days} 天免费试用
              </div>
            )}

            <button
              onClick={() => !isActive && setChannelModal(plan)}
              disabled={isActive || isLoading}
              style={{
                width: "100%", padding: "10px 0", borderRadius: 8,
                background: isActive ? "#ccc" : "#0088cc",
                color: "#fff", border: "none",
                cursor: isActive ? "default" : "pointer",
                fontSize: 14,
              }}
            >
              {isLoading ? "处理中..." : isActive ? "当前套餐" : "立即订阅"}
            </button>
          </div>
        );
      })}

      {/* 支付渠道选择弹窗 */}
      {channelModal && (
        <ChannelModal
          plan={channelModal}
          onClose={() => setChannelModal(null)}
          onStars={() => handleStars(channelModal)}
          onThirdParty={(ch) => handleThirdParty(channelModal, ch)}
        />
      )}

      {/* 微信二维码弹窗 */}
      {wechatOrder && (
        <WechatQrModal
          order={wechatOrder}
          qrcodeUrl={api.wechatQrcodeUrl(wechatOrder.out_trade_no)}
          onClose={() => setWechatOrder(null)}
          onPaid={() => { setWechatOrder(null); fetchSubscription(); }}
        />
      )}
    </div>
  );
}
