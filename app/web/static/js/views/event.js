import { controls, coverStyle, escapeHtml, eventRow, status } from "../components/events.js?v=20260527-polished-search-gradient";
import { formatEventDate, t } from "../i18n.js?v=20260527-polished-search-gradient";

function meta(label, value) {
  return `
    <div class="meta">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value || "—")}</span>
    </div>
  `;
}

export function renderEvent(event) {
  if (!event) {
    return `
      <div class="screen">
        <header class="cover compact" ${coverStyle(null, "header-main")}>${controls()}<p class="eyebrow">${t("events")}</p><h1>${t("unavailable")}</h1></header>
        <main class="content">${status(t("unavailable"))}</main>
      </div>
    `;
  }

  const eventDate = new Date(`${event.date}T${event.time || "00:00"}:00`);
  const isEnded = !isNaN(eventDate.getTime()) && eventDate < new Date();

  return `
    <div class="screen event-screen" data-route="event" data-token="${escapeHtml(event.token)}" data-palette="${escapeHtml(event.palette_key)}">
      <header class="cover ${event.cover_url ? "has-cover" : ""}" ${coverStyle(event.cover_url, `event-detail-${event.token || event.title}`)}>
        ${controls()}
        <button class="favorite-toggle ${event.is_favorite ? "active" : ""}" type="button" data-action="favorite" aria-label="Favorite">
          <span>★</span>
        </button>
        <h1>${escapeHtml(event.title)}</h1>
      </header>
      <main class="content">
        <section class="panel meta-grid">
          ${meta(t("dateTime"), formatEventDate(event))}
          ${meta(t("location"), event.location)}
          ${meta(t("organizer"), event.organizer)}
          ${meta(t("attendees"), String(event.attendee_count || 0))}
        </section>

        ${event.registration_url ? `<section class="panel action-panel"><button class="action register-action" type="button" data-action="register">${t("register")}</button></section>` : ""}

        <section class="panel">
          <p class="description">${escapeHtml(event.description || "")}</p>
        </section>

        <section class="panel action-panel">
          <div class="event-actions">
            <button class="action" type="button" data-action="reminder" ${isEnded ? "disabled" : ""}>${t("addReminder")}</button>
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
