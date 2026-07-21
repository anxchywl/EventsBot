import { currentTheme, setTheme } from "./state.js?v=20260721-timeline-v7";

export const tg = window.Telegram?.WebApp || null;

// init telegram
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

// mirror telegram theme into app state
export function syncTheme() {
  if (!tg?.colorScheme) {
    document.documentElement.dataset.theme = currentTheme();
    return;
  }
  setTheme(tg.colorScheme === "dark" ? "dark" : "light");
}

// init data
export function initData() {
  return tg?.initData || "";
}

// start param
export function startParam() {
  return sanitizeStartPayload(tg?.initDataUnsafe?.start_param || "");
}

// limit start payloads before routing
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

// haptic
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

// guard haptic calls across partial telegram webviews
function callHaptic(run) {
  try {
    run();
  } catch {
    // some android webviews expose partial telegram haptic apis that throw
  }
}

// fallback to native vibration when haptics are unavailable
function vibrate(pattern) {
  try {
    window.navigator?.vibrate?.(pattern);
  } catch {
    // native vibration is best-effort and unavailable in some telegram clients
  }
}

// open telegram-native links through the web app bridge
export function openTelegramLink(url) {
  if (!isSafeTelegramUrl(url)) {
    return;
  }
  // t.me/share links are not supported by tg.openTelegramLink and will do nothing.
  // We must open them using tg.openLink (which opens the browser/in-app share popup)
  if (url.includes("t.me/share/")) {
    if (tg?.openLink) {
      tg.openLink(url);
      return;
    }
    window.location.href = url;
    return;
  }
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  window.location.href = url;
}

// open safe external links through telegram when possible
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

// allow only safe http links for external navigation
function isSafeHttpUrl(url) {
  try {
    const parsed = new URL(String(url || ""), window.location.origin);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

// allow only safe telegram links
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

// sync telegram back button state
export function configureBackButton(visible, onClick) {
  if (!tg?.BackButton) {
    return;
  }
  try {
    // avoid duplicate telegram back handlers
    if (tg.BackButton.offClick) {
      tg.BackButton.offClick();
    }
  } catch (e) {
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
    }
  }
}
