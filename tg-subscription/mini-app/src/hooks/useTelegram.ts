import { useEffect } from "react";

export function useTelegram() {
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    tg?.ready();
    tg?.expand();
    tg?.setBackgroundColor?.("#ffffff");
    tg?.setHeaderColor?.("#ffffff");
  }, []);

  const openInvoice = (link: string, onPaid: () => void) => {
    tg?.openInvoice(link, (status) => {
      if (status === "paid") {
        tg.HapticFeedback?.notificationOccurred("success");
        onPaid();
      } else if (status === "failed") {
        tg?.showPopup({ message: "支付未完成，请重试。" });
      }
    });
  };

  return {
    user: tg?.initDataUnsafe?.user,
    colorScheme: tg?.colorScheme ?? "light",
    openInvoice,
    openLink: (url: string) => tg?.openLink(url),
    close: () => tg?.close(),
  };
}
