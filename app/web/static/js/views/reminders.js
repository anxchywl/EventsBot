import { controls, coverStyle, escapeAttr, escapeHtml, nav } from "../components/events.js?v=20260525-card-spacing-align";
import { t } from "../i18n.js?v=20260525-card-spacing-align";
import { state } from "../state.js";

function formatReminderGroupDate(date) {
  const value = new Date(`${date}T00:00:00`);
  if (Number.isNaN(value.getTime())) return date;
  return new Intl.DateTimeFormat(state.lang || "en", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(value);
}

function formatReminderLeadTime(minutes) {
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  const parts = [];
  if (days) parts.push(`${days} ${days === 1 ? "day" : "days"}`);
  if (hours) parts.push(`${hours} ${hours === 1 ? "hour" : "hours"}`);
  if (mins) parts.push(`${mins} ${mins === 1 ? "minute" : "minutes"}`);
  return parts.join(" ") || "0 minutes";
}

function reminderKey(reminder) {
  return reminder?.event?.token || reminder?.event?.title || "";
}

function groupRemindersByEvent(reminders) {
  const grouped = new Map();
  reminders.forEach((reminder) => {
    const key = reminderKey(reminder);
    if (!grouped.has(key)) {
      grouped.set(key, {
        event: reminder.event,
        reminders: [],
      });
    }
    grouped.get(key).reminders.push(reminder);
  });
  return [...grouped.values()].map((group) => ({
    ...group,
    reminders: group.reminders
      .slice()
      .sort((a, b) => b.offset_minutes - a.offset_minutes)
      .slice(0, 3),
  }));
}

function reminderCard(group) {
  return `
    <article class="reminder-card" data-event-token="${escapeAttr(group.event.token)}">
      <div class="reminder-card-cover ${group.event.cover_url ? "has-image" : ""}" ${coverStyle(group.event.cover_url, `event-${group.event.token || group.event.title}`)}></div>
      <div class="reminder-card-main">
        <strong>${escapeHtml(group.event.title)}</strong>
        <div class="reminder-times">
          ${group.reminders
            .map(
              (reminder) => `
                <div class="reminder-time-row">
                  <span>${escapeHtml(`${formatReminderLeadTime(reminder.offset_minutes)} before the event`)}</span>
                  <button class="reminder-remove-button" type="button" data-reminder-id="${escapeAttr(reminder.id)}" aria-label="${escapeAttr(t("remove"))}">×</button>
                </div>
              `,
            )
            .join("")}
        </div>
      </div>
    </article>
  `;
}

export function renderReminders(groups) {
  return `
    <div class="screen" data-route="reminders">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        ${controls()}
        <h1>${t("reminders")}</h1>
      </header>
      <main class="content">
        ${nav("reminders")}
        ${
          groups.length
            ? groups
                .map(
                  (group) => `
                    <section class="panel">
                      <h2 class="section-title">${escapeHtml(formatReminderGroupDate(group.date))}</h2>
                      <div class="reminder-card-list">
                        ${groupRemindersByEvent(group.reminders).map(reminderCard).join("")}
                      </div>
                    </section>
                  `,
                )
                .join("")
            : `
              <div class="empty-page-state">
                <svg class="empty-page-icon" viewBox="0 0 24 24"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" fill="currentColor"/></svg>
                <p class="empty-page-text">${escapeHtml(t("emptyReminders"))}</p>
              </div>
            `
        }
      </main>
    </div>
  `;
}
