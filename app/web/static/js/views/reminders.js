import { controls, coverStyle, escapeAttr, escapeHtml, nav } from "../components/events.js?v=20260528-sanitize-spaces-v2";
import { t } from "../i18n.js?v=20260528-sanitize-spaces-v2";

function formatReminderLeadTime(minutes) {
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  const parts = [];
  if (days) parts.push(formatReminderUnit(days, "day"));
  if (hours) parts.push(formatReminderUnit(hours, "hour"));
  if (mins) parts.push(formatReminderUnit(mins, "minute"));
  return parts.join(" ") || t("zeroMinutes");
}

function formatReminderUnit(value, unit) {
  const key = value === 1 ? `${unit}One` : `${unit}Many`;
  return `${value} ${t(key)}`;
}

function formatReminderBeforeEvent(minutes) {
  return t("beforeEvent").replace("{time}", formatReminderLeadTime(minutes));
}

function reminderKey(reminder) {
  return reminder?.event?.token || reminder?.event?.title || "";
}

function flattenReminderGroups(groups) {
  return groups.flatMap((group) => group.reminders || []);
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
    <article class="reminder-card" role="button" tabindex="0" data-event-token="${escapeAttr(group.event.token)}">
      <div class="reminder-card-cover ${group.event.cover_url ? "has-image" : ""}" ${coverStyle(group.event.cover_url, `event-${group.event.token || group.event.title}`)}></div>
      <div class="reminder-card-main">
        <strong>${escapeHtml(group.event.title)}</strong>
        <div class="reminder-times">
          ${group.reminders
            .map(
              (reminder) => `
                <div class="reminder-time-row">
                  <span>${escapeHtml(formatReminderBeforeEvent(reminder.offset_minutes))}</span>
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
  const eventGroups = groupRemindersByEvent(flattenReminderGroups(groups));

  return `
    <div class="screen" data-route="reminders">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        <h1>${t("reminders")}</h1>
      </header>
      <main class="content">
        ${
          eventGroups.length
            ? `
              <section class="panel">
                <div class="reminder-card-list">
                  ${eventGroups.map(reminderCard).join("")}
                </div>
              </section>
            `
            : `
              <div class="empty-page-state">
                <svg class="empty-page-icon" viewBox="0 0 24 24"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" fill="currentColor"/></svg>
                <p class="empty-page-text">${escapeHtml(t("emptyReminders"))}</p>
              </div>
            `
        }
      </main>
      ${nav("reminders")}
    </div>
  `;
}
