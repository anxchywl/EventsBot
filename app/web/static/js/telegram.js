import { currentTheme, setTheme } from "./state.js?v=20260607-cal-v15";

export const tg = window.Telegram?.WebApp || null;

export function initTelegram(onThemeChange) {
  if (!tg) {
    document.documentElement.dataset.theme = currentTheme();
    return;
  }
  tg.ready();
  syncTheme();
  tg.onEvent?.("themeChanged", () => {
    syncTheme();
    onThemeChange?.();
  });
}

export function syncTheme() {
  if (!tg?.colorScheme) {
    document.documentElement.dataset.theme = currentTheme();
    return;
  }
  setTheme(tg.colorScheme === "dark" ? "dark" : "light");
}

export function initData() {
  return tg?.initData || "";
}

export function startParam() {
  return sanitizeStartPayload(tg?.initDataUnsafe?.start_param || "");
}

export function sanitizeStartPayload(value) {
  const payload = String(value || "").trim();
  if (/^event_[0-9a-fA-F-]{36}$/.test(payload)) {
    return payload;
  }
  if (/^invite_[A-Za-z0-9_-]{32,256}$/.test(payload)) {
    return payload;
  }
  return "";
}

export function haptic(type = "selection") {
  if (type === "impact") {
    callHaptic(() => tg?.HapticFeedback?.impactOccurred?.("medium"));
    callHaptic(() => tg?.HapticFeedback?.selectionChanged?.());
    vibrate(24);
    return;
  }
  if (type === "light") {
    callHaptic(() => tg?.HapticFeedback?.impactOccurred?.("light"));
    callHaptic(() => tg?.HapticFeedback?.selectionChanged?.());
    vibrate(12);
    return;
  }
  if (type === "success") {
    callHaptic(() => tg?.HapticFeedback?.notificationOccurred?.("success"));
    vibrate([18, 24, 18]);
    return;
  }
  if (type === "error") {
    callHaptic(() => tg?.HapticFeedback?.notificationOccurred?.("error"));
    vibrate([30, 20, 30]);
    return;
  }
  callHaptic(() => tg?.HapticFeedback?.selectionChanged?.());
  vibrate(10);
}

function callHaptic(run) {
  try {
    run();
  } catch {
    // Some Android WebViews expose partial Telegram haptic APIs that throw.
  }
}

function vibrate(pattern) {
  try {
    window.navigator?.vibrate?.(pattern);
  } catch {
    // Native vibration is best-effort and unavailable in some Telegram clients.
  }
}

export function openTelegramLink(url) {
  if (!isSafeTelegramUrl(url)) {
    return;
  }
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  window.location.href = url;
}

export function openLink(url) {
  if (!isSafeHttpUrl(url)) {
    return;
  }
  if (tg?.openLink) {
    tg.openLink(url);
    return;
  }
  window.open(url, "_blank", "noopener");
}

function isSafeHttpUrl(url) {
  try {
    const parsed = new URL(String(url || ""), window.location.origin);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function isSafeTelegramUrl(url) {
  try {
    const value = String(url || "");
    const parsed = new URL(value, window.location.origin);
    return (
      parsed.protocol === "tg:"
      || (parsed.protocol === "https:" && parsed.hostname === "t.me")
      || (parsed.protocol === "https:" && parsed.hostname.endsWith(".telegram.me"))
    );
  } catch {
    return false;
  }
}

export function configureBackButton(visible, onClick) {
  if (!tg?.BackButton) {
    return;
  }
  try {
    // Always try to remove previous handler first
    if (tg.BackButton.offClick) {
      tg.BackButton.offClick();
    }
  } catch (e) {
    // Silently ignore errors when removing handler
  }
  
  if (visible) {
    try {
      tg.BackButton.show();
      tg.BackButton.onClick(onClick);
    } catch (e) {
      console.error("Error configuring back button:", e);
    }
  } else {
    try {
      tg.BackButton.hide();
    } catch (e) {
      // Silently ignore errors when hiding
    }
  }
}
