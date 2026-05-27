import { state } from "../state.js";
import { categoryLabel, t } from "../i18n.js?v=20260527-no-event-filter-haptics";

const fallbackCoverStyles = new Map();

export function resetFallbackCoverStyles() {
  fallbackCoverStyles.clear();
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function randomCoverVariables() {
  const dark = document.documentElement.dataset.theme === "dark";
  const h1 = Math.floor(Math.random() * 360);
  const h2 = (h1 + 60 + Math.floor(Math.random() * 120)) % 360;
  const h3 = (h2 + 60 + Math.floor(Math.random() * 120)) % 360;
  const h4 = (h3 + 60 + Math.floor(Math.random() * 120)) % 360;
  const sat = 88 + Math.floor(Math.random() * 13);  // 88–100% for both themes
  const light = dark ? 58 + Math.floor(Math.random() * 18) : 60 + Math.floor(Math.random() * 16);
  const glowLight = dark ? 72 + Math.floor(Math.random() * 16) : 80 + Math.floor(Math.random() * 12);
  const accentLight = dark ? 62 + Math.floor(Math.random() * 16) : 66 + Math.floor(Math.random() * 14);
  const angle = Math.floor(Math.random() * 360);
  const first = `hsl(${h1} ${sat}% ${light}%)`;
  const second = `hsl(${h2} ${sat}% ${light}%)`;
  const glow = `hsl(${h3} ${sat}% ${glowLight}%)`;
  const accent = `hsl(${h4} ${sat}% ${accentLight}%)`;
  return `--fallback-angle: ${angle}deg; --fallback-a: ${escapeAttr(first)}; --fallback-b: ${escapeAttr(second)}; --fallback-c: ${escapeAttr(glow)}; --fallback-d: ${escapeAttr(accent)}`;
}

export function coverStyle(url, key = "") {
  if (url) {
    return `style="--cover-image: url('${escapeAttr(url)}')"`;
  }
  const cacheKey = key || `cover-${fallbackCoverStyles.size}`;
  if (!fallbackCoverStyles.has(cacheKey)) {
    fallbackCoverStyles.set(cacheKey, randomCoverVariables());
  }
  return `style="${fallbackCoverStyles.get(cacheKey)}"`;
}

function eventTimestamp(event) {
  const value = new Date(`${event.date}T${event.time || "00:00"}:00`);
  return Number.isNaN(value.getTime()) ? "" : String(value.getTime());
}

export function controls() {
  return `
    <div class="top-controls">
      <button class="theme-toggle" type="button" data-action="theme" aria-label="Theme">
        <svg class="sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path></svg>
        <svg class="moon" viewBox="0 0 24 24"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8z"></path></svg>
      </button>
      <button class="lang-toggle" type="button" data-action="lang">${escapeHtml(state.lang.toUpperCase())}</button>
    </div>
  `;
}

export function nav(active) {
  const items = [
    ["events", `<svg class="nav-icon" viewBox="0 0 24 24" width="20" height="20"><path d="M19 4H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z" fill="currentColor"/></svg>`],
    ["reminders", `<svg class="nav-icon" viewBox="0 0 24 24" width="20" height="20"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" fill="currentColor"/></svg>`],
  ];
  return `
    <nav class="app-nav" aria-label="Mini app navigation">
      ${items
        .map(
          ([route, icon]) => `
            <button class="nav-pill nav-circle ${active === route ? "active" : ""}" type="button" data-route="${route}">
              ${icon}
            </button>
          `,
        )
        .join("")}
    </nav>
  `;
}

export function eventRow(event, options = {}) {
  const {
    showDateLocation = true,
    showCountdown = true,
    showFavoriteBadge = true,
    showReminderBadge = true,
    badgesOnSide = true,
    showFavoriteAction = false,
  } = options;
  return `
    <article class="event-row ${badgesOnSide ? "has-side-badges" : ""} ${showFavoriteAction ? "has-favorite-action" : ""} ${event.is_archived ? "archived" : event.is_ended ? "ended" : ""}" role="button" tabindex="0" data-event-token="${escapeAttr(event.token)}">
      <div class="event-row-cover ${event.cover_url ? "has-image" : ""}" ${coverStyle(event.cover_url, `event-${event.token || event.title}`)}></div>
      <div class="event-row-body">
        ${showCountdown ? `<span class="event-countdown" data-countdown-target="${escapeAttr(eventTimestamp(event))}"></span>` : ""}
        <strong>${escapeHtml(event.title)}</strong>
        ${showDateLocation ? `<span>${escapeHtml(event.organizer || "")}</span>` : ""}
        ${showDateLocation ? `<span>${escapeHtml(event.location || "")}</span>` : ""}
      </div>
      <div class="row-badges">
        <em>${escapeHtml(categoryLabel(event.category))}</em>
        ${showFavoriteBadge && event.is_favorite ? `<em data-favorite-badge>★</em>` : ""}
        ${showReminderBadge && event.reminder_count ? `<em>${event.reminder_count}</em>` : ""}
      </div>
      ${showFavoriteAction ? `<button class="favorite-remove-button active" type="button" data-favorite-remove="${escapeAttr(event.token)}" aria-label="${t("remove")}"><span>★</span></button>` : ""}
    </article>
  `;
}


export function formatCountdown(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (days > 0) {
    return [days, hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }
  if (hours > 0) {
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }
  if (minutes > 0) {
    return [minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }
  return String(seconds).padStart(2, "0");
}

let countdownTimer = null;

export function startCountdowns(root = document) {
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
    countdownTimer = null;
  }

  const update = () => {
    const now = Date.now();
    root.querySelectorAll("[data-countdown-target]").forEach((el) => {
      const target = Number(el.dataset.countdownTarget || 0);
      if (!target || target <= now) {
        el.hidden = true;
        el.textContent = "";
        return;
      }
      el.hidden = false;
      el.textContent = formatCountdown(target - now);
    });
  };

  update();
  if (root.querySelector("[data-countdown-target]")) {
    countdownTimer = window.setInterval(update, 1000);
  }
}

export function status(message) {
  return `<div class="panel status">${escapeHtml(message)}</div>`;
}

export function loadingScreen(title = t("loading")) {
  return `
    <div class="screen">
      <div class="cover skeleton compact"></div>
      <main class="content">
        <div class="panel">
          <div class="line skeleton wide"></div>
          <div class="line skeleton"></div>
          <div class="grid">
            <div class="tile skeleton"></div>
            <div class="tile skeleton"></div>
          </div>
          <span class="sr-only">${escapeHtml(title)}</span>
        </div>
      </main>
    </div>
  `;
}
