const tg = window.Telegram?.WebApp;
const BASE_URL = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Init-Data": tg?.initData ?? "",
      ...options.headers,
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const api = {
  getPlans: () => request<{ data: Plan[] }>("/plans"),

  getCurrentSubscription: () =>
    request<{ data: Subscription | null }>("/subscriptions/current"),

  // Stars 支付（Telegram 原生）
  createInvoice: (plan_id: string) =>
    request<{ data: { invoice_link: string; subscription_id: number } }>(
      "/payments/invoice",
      { method: "POST", body: JSON.stringify({ plan_id }) }
    ),

  // 微信 / 支付宝支付
  createThirdPartyPayment: (plan_id: string, channel: "wechat" | "alipay") =>
    request<{ data: ThirdPartyPayResult }>("/pay/create", {
      method: "POST",
      body: JSON.stringify({ plan_id, channel }),
    }),

  // 轮询支付状态
  getPaymentStatus: (out_trade_no: string) =>
    request<{ data: { status: string; out_trade_no: string } }>(
      `/pay/status/${out_trade_no}`
    ),

  // 微信二维码图片 URL（直接用于 <img src=> ）
  wechatQrcodeUrl: (out_trade_no: string) =>
    `${BASE_URL}/api/v1/pay/qrcode/${out_trade_no}`,
};

export interface Plan {
  id: string;
  name: string;
  description: string;
  stars_price: number;
  cny_price_fen: number;   // 0 = 未开通人民币支付
  billing_cycle: string;
  trial_days: number;
  features: string[];
}

export interface Subscription {
  id: number;
  plan_id: string;
  plan_name: string;
  status: string;
  expires_at: string;
  tier: string;
}

export interface ThirdPartyPayResult {
  channel: "wechat" | "alipay";
  out_trade_no: string;
  amount_fen: number;
  amount_cny: string;
  expires_at: string;
  // 微信专有
  code_url?: string;
  // 支付宝专有
  pay_url?: string;
}
