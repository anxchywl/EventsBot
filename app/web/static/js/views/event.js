import { controls, coverStyle, escapeAttr, escapeHtml, eventRow, status } from "../components/events.js?v=20260527-no-event-filter-haptics";
import { formatEventDate, t } from "../i18n.js?v=20260527-no-event-filter-haptics";

function meta(label, value, copyable = false) {
  const displayValue = value || "—";
  return `
    <div class="meta ${copyable ? "copyable" : ""}" ${copyable ? `role="button" tabindex="0" data-copy-value="${escapeAttr(displayValue)}" aria-label="${escapeAttr(label)}"` : ""}>
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(displayValue)}</span>
    </div>
  `;
}

export function renderEvent(event) {
  if (!event) {
    return "";
  }
  const isArchived = event.is_archived || event.is_ended;

  return `
    <div class="screen event-screen ${event.is_archived ? "archived" : ""}" data-route="event" data-token="${escapeHtml(event.token)}" data-palette="${escapeHtml(event.palette_key)}">
      <header class="cover ${event.cover_url ? "has-cover" : ""}" ${coverStyle(event.cover_url, `event-detail-${event.token || event.title}`)}>
        <button class="favorite-toggle ${event.is_favorite ? "active" : ""}" type="button" data-action="favorite" aria-label="Favorite">
          <span>★</span>
        </button>
        <h1>${escapeHtml(event.title)}</h1>
      </header>
      <main class="content">
        <section class="panel meta-grid">
          ${meta(t("dateTime"), formatEventDate(event), true)}
          ${meta(t("location"), event.location, true)}
          ${meta(t("organizer"), event.organizer, true)}
          ${meta(t("attendees"), String(event.attendee_count || 0))}
        </section>

        ${event.registration_url ? `<section class="panel action-panel"><button class="action register-action" type="button" data-action="register" ${isArchived ? "disabled" : ""}>${t("register")}</button></section>` : ""}

        <section class="panel">
          <p class="description">${escapeHtml(event.description || "")}</p>
        </section>

        <section class="panel action-panel">
          <div class="event-actions">
            <button class="action" type="button" data-action="reminder" ${isArchived ? "disabled" : ""}>${t("addReminder")}</button>
            <button class="action primary" type="button" data-action="share">${t("share")}</button>
          </div>
        </section>

        ${
          event.related_events?.length
            ? `<section class="panel"><h2 class="section-title">${t("related")}</h2>${event.related_events.map(eventRow).join("")}</section>`
            : ""
        }
      </main>
    </div>
  `;
}

export function renderEventUnavailable() {
  return `
    <div class="screen">
      <header class="cover compact" ${coverStyle(null, "header-main")}><h1>${t("unavailable")}</h1></header>
      <main class="content">${status(t("unavailable"))}</main>
    </div>
  `;
}

export function renderEventSkeleton(token) {
  return `
    <div class="screen event-screen skeleton-screen" data-route="event" data-token="${escapeHtml(token)}">
      <header class="cover has-cover" ${coverStyle(null, `event-detail-${token}`)}>
        <button class="favorite-toggle" type="button" disabled aria-label="Favorite">
          <span>★</span>
        </button>
        <h1><div class="line skeleton wide title-skeleton" style="margin: 0; display: inline-block;"></div></h1>
      </header>
      <main class="content">
        <section class="panel meta-grid">
          ${meta(t("dateTime"), '<div class="line skeleton"></div>')}
          ${meta(t("location"), '<div class="line skeleton"></div>')}
          ${meta(t("organizer"), '<div class="line skeleton"></div>')}
          ${meta(t("attendees"), '<div class="line skeleton"></div>')}
        </section>
        <section class="panel action-panel">
          <div class="event-actions">
            <button class="action skeleton" type="button" disabled>&nbsp;</button>
            <button class="action primary skeleton" type="button" disabled>&nbsp;</button>
          </div>
        </section>
      </main>
    </div>
  `;
}
