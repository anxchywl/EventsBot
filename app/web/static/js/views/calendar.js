import { addFavorite, createReminder, removeFavorite } from "../api.js";
import { coverStyle, escapeAttr, escapeHtml, nav } from "../components/events.js?v=20260529-flicker-fix-v10";
import { openReminderSheet } from "../components/sheets.js?v=20260529-flicker-fix-v10";
import { t } from "../i18n.js?v=20260529-flicker-fix-v10";
import { state } from "../state.js";
import { haptic } from "../telegram.js";

const MONTH_RANGE = 12; // -12 to +12 = 25 months
const monthGridCache = new Map();
let activeAbortController = null;
let favoriteRequestToken = "";

export function isEventArchived(event) {
  if (event.is_archived || event.is_ended) return true;
  const now = new Date();
  const todayStr = localDateKey(now);
  if (event.date < todayStr) return true;
  if (event.date === todayStr && event.time) {
    const [h, m] = event.time.split(":").map(Number);
    const eventTime = new Date();
    eventTime.setHours(h, m, 0, 0);
    const eventEnd = new Date(eventTime.getTime() + 2 * 60 * 60 * 1000);
    return eventEnd < now;
  }
  return false;
}

export function isEventLive(event) {
  if (event.is_archived || event.is_ended) return false;
  const now = new Date();
  const todayStr = localDateKey(now);
  if (event.date !== todayStr) return false;
  if (!event.time) return true;
  const [h, m] = event.time.split(":").map(Number);
  const eventStart = new Date();
  eventStart.setHours(h, m, 0, 0);
  const eventEnd = new Date(eventStart.getTime() + 2 * 60 * 60 * 1000);
  return now >= eventStart && now <= eventEnd;
}

function isEventTrending(event) {
  return event.is_trending || (event.attendee_count && event.attendee_count > 15);
}

function eventSignature(events) {
  return events
    .map((event) => [
      event.token,
      event.date,
      event.time || "",
      event.is_favorite ? "1" : "0",
      event.is_archived || event.is_ended ? "1" : "0",
      event.reminder_count || 0,
    ].join(":"))
    .join("|");
}

function monthKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function localDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parseDate(value) {
  const date = new Date(value || Date.now());
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function monthDate(dateStr, offset = 0) {
  const date = parseDate(dateStr);
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

function monthIso(dateStr, offset = 0) {
  return monthDate(dateStr, offset).toISOString();
}

function formatMonth(date) {
  return new Intl.DateTimeFormat(state.lang || "en", {
    month: "long",
    year: "numeric",
  }).format(date);
}

function eventsForDay(events, dateStr) {
  return events
    .filter((event) => event.date === dateStr)
    .sort((a, b) => (a.time || "").localeCompare(b.time || ""));
}

function renderMonthGrid(events, date) {
  const signature = eventSignature(events);
  const cacheKey = `${monthKey(date)}:${state.lang}:${signature}`;
  const cached = monthGridCache.get(cacheKey);
  if (cached) return cached;

  const year = date.getFullYear();
  const month = date.getMonth();
  const isMondayFirst = state.lang === "ru" || state.lang === "kk";
  const rawFirstDay = new Date(year, month, 1).getDay();
  const firstDay = isMondayFirst ? (rawFirstDay + 6) % 7 : rawFirstDay;

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const todayStr = localDateKey(new Date());
  const dayNames = shortWeekDays();
  let html = `
    <div class="calendar-month-grid" data-month-key="${escapeAttr(monthKey(date))}">
      <div class="calendar-day-headers">
        ${dayNames.map((day) => `<span>${escapeHtml(day)}</span>`).join("")}
      </div>
      <div class="calendar-days">
  `;

  for (let i = 0; i < firstDay; i += 1) {
    html += `<div class="calendar-day empty" aria-hidden="true"></div>`;
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayEvents = eventsForDay(events, dateStr);
    const hasEvents = dayEvents.length > 0;
    
    let intensityClass = "";
    if (hasEvents) {
      const activeEvents = dayEvents.filter(e => !isEventArchived(e)).length;
      if (activeEvents > 0) {
        if (activeEvents <= 2) {
          intensityClass = "intensity-low";
        } else if (activeEvents <= 4) {
          intensityClass = "intensity-med";
        } else {
          intensityClass = "intensity-high";
        }
      }
    }

    const favCount = dayEvents.filter(e => e.is_favorite).length;
    let favGlowClass = "";
    if (favCount > 0) {
      if (favCount <= 1) favGlowClass = "fav-glow-low";
      else if (favCount <= 2) favGlowClass = "fav-glow-med";
      else favGlowClass = "fav-glow-high";
    }

    const classes = [
      "calendar-day",
      dateStr === todayStr ? "is-today" : "",
      hasEvents ? "has-events" : "",
      intensityClass,
      dayEvents.some(isEventLive) ? "live-pulse" : "",
      hasEvents && dayEvents.every(isEventArchived) ? "archived-faded" : "",
    ].filter(Boolean).join(" ");

    html += `
      <button class="${classes}" type="button" data-calendar-day="${escapeAttr(dateStr)}" aria-label="${escapeAttr(dayLabel(dateStr, dayEvents.length))}">
        <span class="day-num ${favGlowClass}">${day}</span>
      </button>
    `;
  }

  html += `</div></div>`;
  monthGridCache.set(cacheKey, html);
  if (monthGridCache.size > 18) {
    monthGridCache.delete(monthGridCache.keys().next().value);
  }
  return html;
}

function shortWeekDays() {
  const isMondayFirst = state.lang === "ru" || state.lang === "kk";
  const base = isMondayFirst ? new Date(2026, 1, 2) : new Date(2026, 1, 1);
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(base);
    date.setDate(base.getDate() + index);
    return new Intl.DateTimeFormat(state.lang || "en", { weekday: "narrow" }).format(date);
  });
}

function dayLabel(dateStr, count) {
  const date = new Date(`${dateStr}T00:00:00`);
  const formatted = new Intl.DateTimeFormat(state.lang || "en", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(date);
  return count ? `${formatted}, ${count} ${count === 1 ? "event" : "events"}` : formatted;
}

export function renderCalendarInner(events) {
  const currentDate = new Date();
  state.calendarState.currentDate = currentDate.toISOString();
  state.calendarState.viewMode = "month";

  let html = `
    <div class="calendar-widget-container" data-calendar-scroll>
      <div class="calendar-scroll-content">
  `;

  for (let offset = -MONTH_RANGE; offset <= MONTH_RANGE; offset++) {
    const date = monthDate(currentDate.toISOString(), offset);
    const mKey = monthKey(date);
    html += `
      <section class="month-section" data-month-offset="${offset}" data-month-key="${escapeAttr(mKey)}">
        <div class="sticky-month-header">${escapeHtml(formatMonth(date))}</div>
        <div class="month-grid-placeholder" data-month-placeholder="${offset}"></div>
      </section>
    `;
  }

  html += `
      </div>
    </div>
  `;
  return html;
}

export function attachCalendarInteractions() {
  activeAbortController?.abort();
  activeAbortController = new AbortController();
  const { signal } = activeAbortController;
  
  const scrollContainer = document.querySelector("[data-calendar-scroll]");
  if (!scrollContainer) return;

  scrollContainer.addEventListener("click", (event) => {
    const day = event.target.closest("[data-calendar-day]");
    if (!day) return;
    haptic("light");
    state.calendarState.currentDate = `${day.dataset.calendarDay}T00:00:00.000`;
    showDayPreviewBottomSheet(day.dataset.calendarDay, state.events);
  }, { signal });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const placeholder = entry.target;
      if (entry.isIntersecting) {
        const offset = parseInt(placeholder.dataset.monthPlaceholder, 10);
        const date = monthDate(new Date().toISOString(), offset);
        placeholder.innerHTML = renderMonthGrid(state.events, date);
      } else {
        if (placeholder.innerHTML) {
          placeholder.style.minHeight = placeholder.getBoundingClientRect().height + "px";
          placeholder.innerHTML = "";
        }
      }
    });
  }, {
    root: scrollContainer,
    rootMargin: "300px 0px",
  });

  const placeholders = scrollContainer.querySelectorAll("[data-month-placeholder]");
  placeholders.forEach(p => {
    p.style.minHeight = "280px";
    observer.observe(p);
  });
  
  signal.addEventListener("abort", () => {
    observer.disconnect();
  });

  scrollContainer.addEventListener("scroll", () => {
    state.calendarState.scrollTop = scrollContainer.scrollTop;
  }, { passive: true, signal });

  if (typeof state.calendarState.scrollTop === "number") {
    requestAnimationFrame(() => {
      scrollContainer.scrollTop = state.calendarState.scrollTop;
    });
  } else {
    const currentMonthSection = scrollContainer.querySelector('.month-section[data-month-offset="0"]');
    if (currentMonthSection) {
      requestAnimationFrame(() => {
        scrollContainer.scrollTop = currentMonthSection.offsetTop;
      });
    }
  }
}

export function refreshCalendarMonthPanels({ forceVisible = false } = {}) {
  monthGridCache.clear();
  const scrollContainer = document.querySelector("[data-calendar-scroll]");
  if (!scrollContainer) return;
  const placeholders = scrollContainer.querySelectorAll("[data-month-placeholder]");
  let renderedAny = false;
  placeholders.forEach(p => {
    if (p.innerHTML || forceVisible) {
      const offset = parseInt(p.dataset.monthPlaceholder, 10);
      const date = monthDate(new Date().toISOString(), offset);
      p.innerHTML = renderMonthGrid(state.events, date);
      renderedAny = true;
    }
  });
  if (!renderedAny) {
    const current = scrollContainer.querySelector('[data-month-placeholder="0"]') || placeholders[0];
    if (current) {
      const offset = parseInt(current.dataset.monthPlaceholder || "0", 10);
      const date = monthDate(new Date().toISOString(), offset);
      current.innerHTML = renderMonthGrid(state.events, date);
    }
  }
}

function showDayPreviewBottomSheet(dateStr, events) {
  closeDayPreview();
  document.documentElement.classList.add("sheet-open");
  const dayEvents = eventsForDay(events, dateStr);
  const dateObj = new Date(`${dateStr}T00:00:00`);
  const formattedDate = new Intl.DateTimeFormat(state.lang || "en", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(dateObj);
  const backdrop = document.createElement("div");
  backdrop.id = "dayPreviewBackdrop";
  backdrop.className = "telegram-popup-sheet-backdrop";
  const hasEvents = dayEvents.length > 0;
  backdrop.innerHTML = `
      <section class="telegram-popup-sheet${hasEvents ? "" : " compact"}" role="dialog" aria-modal="true" aria-label="${escapeAttr(formattedDate)}">
        <div class="popup-sheet-header${hasEvents ? "" : " no-border"}">
          <div class="popup-sheet-drag-handle"></div>
          <h3>${escapeHtml(formattedDate)}</h3>
        </div>
        <div class="popup-sheet-content">
          ${hasEvents ? dayEvents.map(renderPopupEvent).join("") : `
          <div class="popup-empty-state">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M19 4H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z"/></svg>
            <p>${escapeHtml(t("emptyEvents"))}</p>
          </div>
          `}
        </div>
      </section>
  `;

  document.body.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add("visible"));
  backdrop.addEventListener("click", handlePreviewClick);
}

function renderPopupEvent(event) {
  const isArchived = isEventArchived(event);
  const isLive = isEventLive(event);
  const cardClasses = [
    "popup-event-card",
    isArchived ? "archived-faded" : "",
    isLive ? "live-pulse" : "",
    event.is_favorite ? "fav-glow-card" : "",
  ].filter(Boolean).join(" ");
  return `
    <article class="${cardClasses}" data-preview-event="${escapeAttr(event.token)}">
      <button class="popup-event-main" type="button" data-calendar-event-open="${escapeAttr(event.token)}">
        <span class="popup-event-time">${escapeHtml(event.time || "--:--")}</span>
        <span class="popup-event-body">
          <strong>${escapeHtml(event.title)}</strong>
          <span>${escapeHtml(event.location || "")}</span>
        </span>
        ${isLive ? `<span class="popup-live-badge">LIVE</span>` : ""}
      </button>
    </article>
  `;
}

async function handlePreviewClick(event) {
  if (event.target === event.currentTarget || event.target.closest("[data-day-preview-close]")) {
    closeDayPreview();
    return;
  }

  const open = event.target.closest("[data-calendar-event-open]");
  if (open) {
    const token = open.dataset.calendarEventOpen;
    if (!token) return;
    closeDayPreview();
    window.location.hash = `#/events/${encodeURIComponent(token)}`;
    return;
  }

  const reminder = event.target.closest("[data-calendar-event-reminder]");
  if (reminder) {
    const targetEvent = state.events.find((item) => item.token === reminder.dataset.calendarEventReminder);
    if (!targetEvent) return;
    haptic("impact");
    closeDayPreview();
    openReminderSheet({
      event: targetEvent,
      onSubmit: async (offset) => {
        if (offset) {
          await createReminder(targetEvent.token, offset);
          targetEvent.reminder_count = (targetEvent.reminder_count || 0) + 1;
        }
        haptic("success");
      },
    });
    return;
  }

  const favorite = event.target.closest("[data-calendar-event-favorite]");
  if (favorite) {
    await togglePreviewFavorite(favorite);
  }
}

async function togglePreviewFavorite(button) {
  const token = button.dataset.calendarEventFavorite;
  const targetEvent = state.events.find((item) => item.token === token);
  if (!targetEvent || favoriteRequestToken === token) return;
  favoriteRequestToken = token;
  const previous = Boolean(targetEvent.is_favorite);
  targetEvent.is_favorite = !previous;
  button.disabled = true;
  button.classList.toggle("active", targetEvent.is_favorite);
  button.textContent = targetEvent.is_favorite ? "★" : "☆";
  refreshCalendarMonthPanels();
  haptic("light");
  try {
    if (targetEvent.is_favorite) {
      await addFavorite(token);
    } else {
      await removeFavorite(token);
    }
    haptic("success");
  } catch {
    targetEvent.is_favorite = previous;
    button.classList.toggle("active", previous);
    button.textContent = previous ? "★" : "☆";
    refreshCalendarMonthPanels();
    haptic("error");
  } finally {
    button.disabled = false;
    favoriteRequestToken = "";
  }
}

function closeDayPreview() {
  const current = document.getElementById("dayPreviewBackdrop");
  if (!current) return;
  current.classList.remove("visible");
  if (!document.querySelector(".sheet-backdrop")) {
    document.documentElement.classList.remove("sheet-open");
  }
  window.setTimeout(() => current.remove(), 220);
}
