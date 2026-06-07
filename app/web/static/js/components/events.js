import { state } from "../state.js?v=20260608-auth-v7";
import { categoryLabel, t } from "../i18n.js?v=20260608-auth-v7";

// guarantee fallbackcoverstyles map is shared absolutely via window to avoid potential duplicate es module instances
if (!window.fallbackCoverStyles) {
  window.fallbackCoverStyles = new Map();
}

// clear generated cover styles for deterministic tests
export function resetFallbackCoverStyles() {
  if (window.fallbackCoverStyles) {
    window.fallbackCoverStyles.clear();
  }
}

// escape text before inserting html
export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// format display name
export function formatDisplayName(nickname, email) {
  let namePart = nickname || "";
  if (!namePart && email) {
    namePart = email.split("@")[0];
  }
  
  if (namePart && namePart.includes(".")) {
    const parts = namePart.split(".");
    if (parts.length === 2) {
      const first = parts[0].charAt(0).toUpperCase() + parts[0].slice(1).toLowerCase();
      const last = parts[1].charAt(0).toUpperCase() + parts[1].slice(1).toLowerCase();
      return `${first} ${last}`;
    }
  }
  return nickname || "Unknown";
}

// escape text before inserting attributes
export function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

// generate high-contrast fallback cover colors
function randomCoverVariables() {
  const dark = document.documentElement.dataset.theme === "dark";
  const h1 = Math.floor(Math.random() * 360);
  const h2 = (h1 + 90 + Math.floor(Math.random() * 90)) % 360;  // spaced out by 90-180 deg for high contrast
  const h3 = (h2 + 90 + Math.floor(Math.random() * 90)) % 360;
  const h4 = (h3 + 90 + Math.floor(Math.random() * 90)) % 360;
  const sat = 95 + Math.floor(Math.random() * 6);  // high saturation (95–100%) for maximum vibrancy
  const light = dark ? 60 + Math.floor(Math.random() * 15) : 65 + Math.floor(Math.random() * 15);
  const glowLight = dark ? 74 + Math.floor(Math.random() * 14) : 82 + Math.floor(Math.random() * 10);
  const accentLight = dark ? 64 + Math.floor(Math.random() * 14) : 70 + Math.floor(Math.random() * 12);
  const angle = Math.floor(Math.random() * 360);
  const first = `hsl(${h1} ${sat}% ${light}%)`;
  const second = `hsl(${h2} ${sat}% ${light}%)`;
  const glow = `hsl(${h3} ${sat}% ${glowLight}%)`;
  const accent = `hsl(${h4} ${sat}% ${accentLight}%)`;
  return `--fallback-angle: ${angle}deg; --fallback-a: ${escapeAttr(first)}; --fallback-b: ${escapeAttr(second)}; --fallback-c: ${escapeAttr(glow)}; --fallback-d: ${escapeAttr(accent)}`;
}

// reuse generated cover colors per event
export function coverStyle(url, key = "") {
  if (url) {
    return `style="--cover-image: url('${escapeAttr(url)}')"`;
  }
  const cacheKey = key || `cover-${window.fallbackCoverStyles.size}`;
  if (!window.fallbackCoverStyles.has(cacheKey)) {
    window.fallbackCoverStyles.set(cacheKey, randomCoverVariables());
  }
  return `style="${window.fallbackCoverStyles.get(cacheKey)}"`;
}

// build stable event sort timestamps
function eventTimestamp(event) {
  const value = new Date(`${event.date}T${event.time || "00:00"}:00`);
  return Number.isNaN(value.getTime()) ? "" : String(value.getTime());
}


// derive stable avatar colors from display names
function avatarColor(nickname) {
  let hash = 0;
  for (let i = 0; i < (nickname || "").length; i++) {
    hash = nickname.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 48%)`;
}

// render compact friends-going avatars
export function friendsCarousel(friends) {
  if (!friends || friends.length === 0) return "";

  const MAX_SHOWN = 6;
  const shown = friends.slice(0, MAX_SHOWN);

  const avatarItems = shown.map(friend => {
    const color = avatarColor(friend.nickname || "");
    const avatarContent = friend.avatar?.url
      ? `<img src="${escapeAttr(friend.avatar.url)}" alt="${escapeAttr(friend.nickname)}" loading="lazy">`
      : `<span>${escapeHtml((friend.avatar?.initials || "?").slice(0, 2))}</span>`;
    const actionAttr = friend.telegram_url
      ? `data-open-telegram="${escapeAttr(friend.telegram_url)}"`
      : `data-friend-id="${friend.id}"`;
    return `<div class="fg-avatar" role="button" tabindex="0" ${actionAttr} title="${escapeAttr(friend.nickname)}" style="background:${escapeAttr(color)}">${avatarContent}</div>`;
  }).join("");

  return `
    <div class="friends-going-row">
      <div class="fg-stack">${avatarItems}</div>
    </div>
  `;
}


// render global theme and language controls
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

// render bottom navigation state
export function nav(active) {
  return "";
}

// render one event list row
export function eventRow(event, options = {}) {
  const {
    showDateLocation = true,
    showCountdown = true,
    showFavoriteBadge = true,
    showReminderBadge = true,
    badgesOnSide = true,
    showFavoriteAction = false,
  } = options;
  const categoryText = categoryLabel(event.category);
  return `
    <article class="event-row ${badgesOnSide ? "has-side-badges" : ""} ${showFavoriteAction ? "has-favorite-action" : ""} ${event.is_archived ? "archived" : event.is_ended ? "ended" : ""}" role="button" tabindex="0" data-event-token="${escapeAttr(event.token)}">
      <div class="event-row-cover ${event.cover_url ? "has-image" : ""}" ${coverStyle(event.cover_url, `event-${event.token || event.title}`)}>
        ${event.is_favorite ? `<span class="event-row-favorite-sticker" aria-label="${escapeAttr(t("favorites"))}" role="img">
          <span>★</span>
        </span>` : ""}
      </div>
      <div class="event-row-body">
        <strong>${escapeHtml(event.title)}</strong>
        ${showDateLocation ? `<span>${escapeHtml(event.organizer || "")}</span>` : ""}
        ${showDateLocation ? `<span>${escapeHtml(event.location || "")}</span>` : ""}
        <div class="event-row-top-meta">
          <em>${escapeHtml(categoryText)}</em>
          ${showCountdown ? `<span class="event-countdown" data-countdown-target="${escapeAttr(eventTimestamp(event))}"></span>` : ""}
        </div>
        ${friendsCarousel(event.friends_going)}
      </div>
      ${showFavoriteAction ? `<button class="favorite-remove-button active" type="button" data-favorite-remove="${escapeAttr(event.token)}" aria-label="${t("remove")}"><span>★</span></button>` : ""}
    </article>
  `;
}


// format countdown
export function formatCountdown(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (days > 0) {
    return `${days}${t("timerLabelDays")}`;
  }
  if (hours > 0) {
    return `${hours}${t("timerLabelHours")}`;
  }
  if (minutes > 0) {
    return `${minutes}${t("timerLabelMinutes")}`;
  }
  return `${seconds}${t("timerLabelSeconds")}`;
}

let countdownTimer = null;

// update visible reminder countdowns
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

// render loading status text
export function status(message) {
  return `<div class="panel status">${escapeHtml(message)}</div>`;
}

// render route loading shell
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
