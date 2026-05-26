import { controls, coverStyle, escapeHtml, eventRow, nav, status } from "../components/events.js?v=20260525-card-spacing-align";
import { t } from "../i18n.js?v=20260525-card-spacing-align";
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

export function renderMenu(events) {
  // Sort events by date and time
  const sortedEvents = [...events].sort((a, b) => {
    const dateA = new Date(`${a.date}T${a.time || "00:00"}:00`);
    const dateB = new Date(`${b.date}T${b.time || "00:00"}:00`);
    return dateA - dateB;
  });

  // Group events by date
  const groups = {};
  for (const event of sortedEvents) {
    const key = event.date; // "YYYY-MM-DD"
    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(event);
  }

  const groupKeys = Object.keys(groups).sort();

  const renderedGroups = groupKeys.map(dateStr => {
    const formattedDate = formatGroupDate(dateStr, state.lang);
    const eventCards = groups[dateStr].map(event => eventRow(event, { showDateLocation: true })).join("");
    return `
      <section class="panel event-list">
        <h2 class="section-title">${escapeHtml(formattedDate)}</h2>
        ${eventCards}
      </section>
    `;
  }).join("");

  return `
    <div class="screen" data-route="events">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        ${controls()}
        <h1>${t("events")}</h1>
      </header>
      <main class="content">
        ${nav("events")}
        ${
          sortedEvents.length
            ? renderedGroups
            : `
              <div class="empty-page-state">
                <svg class="empty-page-icon" viewBox="0 0 24 24"><path d="M19 4H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z" fill="currentColor"/></svg>
                <p class="empty-page-text">${escapeHtml(t("emptyEvents"))}</p>
              </div>
            `
        }
      </main>
    </div>
  `;
}

export function renderPlaceholder(active) {
  return `
    <div class="screen" data-route="${active}">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        ${controls()}
        <p class="eyebrow">${t(active)}</p>
        <h1>${t(active)}</h1>
      </header>
      <main class="content">
        ${nav(active)}
        ${status(t(active))}
      </main>
    </div>
  `;
}
