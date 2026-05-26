import { currentTheme, setTheme } from "./state.js";

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
  return tg?.initDataUnsafe?.start_param || "";
}

export function haptic(type = "selection") {
  if (type === "success") {
    tg?.HapticFeedback?.notificationOccurred?.("success");
    return;
  }
  if (type === "error") {
    tg?.HapticFeedback?.notificationOccurred?.("error");
    return;
  }
  tg?.HapticFeedback?.selectionChanged?.();
}

export function openTelegramLink(url) {
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  window.location.href = url;
}

export function openLink(url) {
  if (tg?.openLink) {
    tg.openLink(url);
    return;
  }
  window.open(url, "_blank", "noopener");
}

export function configureBackButton(visible, onClick) {
  if (!tg?.BackButton) {
    return;
  }
  tg.BackButton.offClick?.(onClick);
  if (visible) {
    tg.BackButton.show();
    tg.BackButton.onClick(onClick);
  } else {
    tg.BackButton.hide();
  }
}
