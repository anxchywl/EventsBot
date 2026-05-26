import { controls, coverStyle, escapeHtml, eventRow, nav, status } from "../components/events.js?v=20260525-card-spacing-align";
import { t } from "../i18n.js?v=20260525-card-spacing-align";

export function renderFavorites(events) {
  const active = events.filter((event) => !event.is_ended);
  const ended = events.filter((event) => event.is_ended);
  return `
    <div class="screen" data-route="favorites">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        ${controls()}
        <h1>${t("favorites")}</h1>
      </header>
      <main class="content">
        ${nav("favorites")}
        ${
          events.length
            ? `
              <section class="panel event-list">
                ${active.map((event) => eventRow(event, {
                  showCountdown: false,
                  showDateLocation: true,
                  showFavoriteBadge: false,
                  showReminderBadge: false,
                  badgesOnSide: false,
                  showFavoriteAction: true,
                })).join("")}${ended.map((event) => eventRow(event, {
                  showCountdown: false,
                  showDateLocation: true,
                  showFavoriteBadge: false,
                  showReminderBadge: false,
                  badgesOnSide: false,
                  showFavoriteAction: true,
                })).join("")}
              </section>
            `
            : `
              <div class="empty-page-state">
                <svg class="empty-page-icon" viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" fill="currentColor"/></svg>
                <p class="empty-page-text">${escapeHtml(t("emptyFavorites"))}</p>
              </div>
            `
        }
      </main>
    </div>
  `;
}
