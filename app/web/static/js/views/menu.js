import { controls, coverStyle, escapeAttr, escapeHtml, eventRow, nav, status } from "../components/events.js?v=20260529-flicker-fix-v10";
import { t } from "../i18n.js?v=20260529-flicker-fix-v10";
import { state } from "../state.js";

export function formatGroupDate(dateStr, lang) {
  const date = new Date(`${dateStr}T00:00:00`);
  if (isNaN(date.getTime())) return dateStr;
  return new Intl.DateTimeFormat(lang || "en", {
    day: "numeric",
    month: "long",
    year: "numeric"
  }).format(date);
}

import { renderCalendarInner } from "./calendar.js";

export function renderMenu(events) {
  const isCalendar = state.calendarMode;
  return `
    <div class="screen ${isCalendar ? "calendar-mode-active" : ""}" data-route="events">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        <button class="calendar-toggle-btn ${isCalendar ? "mode-active" : ""}" type="button" data-action="calendar-toggle" aria-label="Calendar">
          <svg class="icon-calendar" viewBox="0 0 24 24" width="22" height="22"><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z" fill="currentColor"/></svg>
          <svg class="icon-list" viewBox="0 0 24 24" width="22" height="22"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z" fill="currentColor"/></svg>
        </button>
        <div class="events-title-block">
          <h1>${isCalendar ? t("eventsCalendar") : t("events")}</h1>
        </div>
      </header>
      <main class="content">
        <div class="events-mode-container ${isCalendar ? "mode-hidden" : ""}">
          ${renderFilterBar()}
          <div data-events-list-region>
            ${renderEventResults(events)}
          </div>
        </div>
        <div class="calendar-mode-container ${!isCalendar ? "mode-hidden" : ""}">
          ${isCalendar ? renderCalendarInner(events) : ""}
        </div>
      </main>
    </div>
  `;
}

function matchesTimeOfDay(eventTime, timeRanges) {
  if (!eventTime) return false;
  const [h, m] = eventTime.split(":").map(Number);
  const mins = h * 60 + (m || 0);

  const morningStart = 6 * 60; // 06:00
  const afternoonStart = 12 * 60; // 12:00
  const eveningStart = 17 * 60; // 17:00
  const nightStart = 22 * 60; // 22:00

  return timeRanges.some(range => {
    if (range === "morning") {
      return mins >= morningStart && mins < afternoonStart;
    }
    if (range === "afternoon") {
      return mins >= afternoonStart && mins < eveningStart;
    }
    if (range === "evening") {
      return mins >= eveningStart && mins < nightStart;
    }
    if (range === "night") {
      return mins >= nightStart || mins < morningStart;
    }
    return false;
  });
}

export function renderEventResults(events) {
  const query = state.eventSearch.query.trim().toLowerCase();
  let sortedEvents = query
    ? events.filter((event) => String(event.title || "").toLowerCase().includes(query))
    : [...events];

  if (state.eventFilters.favoritesOnly) {
    sortedEvents = sortedEvents.filter((event) => event.is_favorite);
  }

  if (state.eventFilters.timeOfDay?.length) {
    sortedEvents = sortedEvents.filter((event) => matchesTimeOfDay(event.time, state.eventFilters.timeOfDay));
  }

  const isTimeSort = state.eventFilters.sort === "time_asc" || state.eventFilters.sort === "time_desc";
  const groups = {};
  if (isTimeSort) {
    for (const event of sortedEvents) {
      const key = event.date;
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(event);
    }
  }

  const groupKeys = Object.keys(groups).sort((a, b) => state.eventFilters.sort === "time_desc" ? b.localeCompare(a) : a.localeCompare(b));

  if (!sortedEvents.length) {
    return `
      <div class="empty-page-state">
        <svg class="empty-page-icon" viewBox="0 0 24 24"><path d="M19 4H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z" fill="currentColor"/></svg>
        <p class="empty-page-text">${escapeHtml(t("emptyEvents"))}</p>
      </div>
    `;
  }

  if (!isTimeSort) {
    return `
      <section class="panel event-list">
        ${sortedEvents.map(event => eventRow(event, { showDateLocation: true })).join("")}
      </section>
    `;
  }

  return groupKeys.map(dateStr => {
    const formattedDate = formatGroupDate(dateStr, state.lang);
    const eventCards = groups[dateStr].map(event => eventRow(event, { showDateLocation: true })).join("");
    return `
      <section class="panel event-list">
        <h2 class="section-title">${escapeHtml(formattedDate)}</h2>
        ${eventCards}
      </section>
    `;
  }).join("");
}

export function renderFilterBar() {
  const filters = state.eventFilters;
  const categoryCount = filters.categories.length;
  const organizerCount = filters.organizers.length;
  const locationCount = filters.locations.length;
  const timeOfDayCount = filters.timeOfDay?.length || 0;
  const relevanceCount = filters.relevance !== "active" ? 1 : 0;
  const isSearching = state.eventSearch.active;
  return `
    <div class="filter-bar-shell ${isSearching ? "search-open" : ""}">
      <div class="filter-bar" aria-label="Event filters">
        ${isSearching ? renderSearchField() : `
          ${searchFilterButton()}
          ${sortFilterButton(filters.sort !== "time_asc")}
          ${filterButton("relevance", filters.relevance === "active" ? t("relevance") : relevanceLabel(filters.relevance), 0, filters.relevance !== "active")}
          ${filterButton("timeOfDay", t("timeOfDay"), timeOfDayCount, timeOfDayCount > 0)}
          ${filterButton("categories", t("categories"), categoryCount, categoryCount > 0)}
          ${filterButton("locations", t("location"), locationCount, locationCount > 0)}
          ${filterButton("organizers", t("organizers"), organizerCount, organizerCount > 0)}
          ${favoriteFilterButton(filters.favoritesOnly)}
        `}
      </div>
    </div>
  `;
}

function searchFilterButton() {
  return `
    <button class="filter-chip filter-chip-icon" type="button" data-action="event-search-open" aria-label="${escapeAttr(t("search"))}">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10.8 18.1a7.3 7.3 0 1 1 0-14.6 7.3 7.3 0 0 1 0 14.6ZM16 16l4.3 4.3" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>
      </svg>
    </button>
  `;
}

function renderSearchField() {
  return `
    <div class="event-search-control">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10.8 18.1a7.3 7.3 0 1 1 0-14.6 7.3 7.3 0 0 1 0 14.6ZM16 16l4.3 4.3" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>
      </svg>
      <input type="search" inputmode="search" autocomplete="off" data-event-search-input maxlength="100" placeholder="${escapeAttr(t("searchEvents"))}" value="${escapeAttr(state.eventSearch.query)}" />
      <button type="button" data-action="event-search-close" aria-label="${escapeAttr(t("cancel"))}">×</button>
    </div>
  `;
}

function sortFilterButton(active) {
  return `
    <button class="filter-chip filter-chip-icon ${active ? "active" : ""}" type="button" data-filter-open="sorting" aria-label="${escapeAttr(t("sorting"))}">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 4v14m0 0 4-4m-4 4-4-4M16 20V6m0 0-4 4m4-4 4 4" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  `;
}

function filterButton(filter, label, count, active) {
  return `
    <button class="filter-chip ${active ? "active" : ""}" type="button" data-filter-open="${filter}">
      <span>${escapeHtml(label)}</span>
      ${count ? `<em>${escapeHtml(count)}</em>` : ""}
    </button>
  `;
}

function favoriteFilterButton(active) {
  return `
    <button class="filter-chip filter-chip-icon favorite-filter-chip ${active ? "active" : ""}" type="button" data-action="favorite-filter-toggle" aria-label="${escapeAttr(t("favorites"))}">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2.8l2.65 5.76 6.3.73-4.66 4.3 1.25 6.21L12 16.69 6.46 19.8l1.25-6.21-4.66-4.3 6.3-.73L12 2.8z" fill="currentColor"/>
      </svg>
    </button>
  `;
}

export function sortLabel(sort) {
  const labels = {
    time_asc: t("nearestFirst"),
    time_desc: t("furthestFirst"),
    reminders_desc: t("mostReminders"),
    reminders_asc: t("leastReminders"),
    participants_desc: t("mostParticipants"),
    participants_asc: t("leastParticipants"),
  };
  return labels[sort] || labels.time_asc;
}

export function relevanceLabel(relevance) {
  const labels = {
    active: t("active"),
    all: t("all"),
    archived: t("archived"),
  };
  return labels[relevance] || labels.active;
}

export function renderPlaceholder(active) {
  return `
    <div class="screen" data-route="${active}">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        <h1>${t(active)}</h1>
      </header>
      <main class="content">
        ${nav(active)}
        ${status(t(active))}
      </main>
    </div>
  `;
}
