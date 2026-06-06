import { escapeHtml, coverStyle, formatDisplayName } from "../components/events.js?v=20260607-cal-v2";
import { state, authHeaders } from "../state.js?v=20260607-cal-v2";
import { t } from "../i18n.js?v=20260607-cal-v2";
import { authenticate } from "../api.js?v=20260607-cal-v2";

async function adminRequest(path, options = {}) {
  await authenticate().catch(() => null);
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(window.Telegram?.WebApp?.initData
        ? { "X-Telegram-Init-Data": window.Telegram.WebApp.initData }
        : {}),
      ...(options.headers || {})
    }
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload?.detail || payload?.message || "Admin request failed");
  }
  return res.json();
}

export async function fetchAdminStats() {
  return adminRequest("/api/admin/stats");
}

export async function fetchAdminUsers(q = "") {
  const params = new URLSearchParams({ limit: "1000" });
  if (q) params.set("q", q);
  const query = `?${params.toString()}`;
  return adminRequest(`/api/admin/users${query}`);
}

export async function fetchConnectedGroups(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status && filters.status !== "all") params.set("status_filter", filters.status);
  if (filters.sort) params.set("sort", filters.sort);
  const query = params.toString();
  return adminRequest(`/api/admin/connected-groups${query ? `?${query}` : ""}`);
}

export async function blockUser(email, reason = "") {
  return adminRequest("/api/admin/users/block", {
    method: "POST",
    body: JSON.stringify({ email, reason })
  });
}

export async function unblockUser(email) {
  return adminRequest("/api/admin/users/unblock", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export function renderAdminPanel(stats, users, connectedGroupsPayload = null) {
  return `
    <div class="screen admin-screen" data-route="admin">
      <header class="cover compact" ${coverStyle(null, "header-admin")}>
        <h1>${t("admin")}</h1>
      </header>
      <main class="content">
        <section class="panel">
          <h2 class="section-title">${t("dashboard")}</h2>
          <div class="stats-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px;">
            <div class="stat-card" style="background: var(--bg-secondary); padding: 15px; border-radius: 12px; text-align: center;">
              <div id="admin-total-bot-users" style="font-size: 24px; font-weight: bold; color: var(--text-primary);">${stats.total_bot_users}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${t("botUsers")}</div>
            </div>
            <div class="stat-card" style="background: var(--bg-secondary); padding: 15px; border-radius: 12px; text-align: center;">
              <div id="admin-total-miniapp-users" style="font-size: 24px; font-weight: bold; color: var(--text-primary);">${stats.total_miniapp_users}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${t("miniAppUsers")}</div>
            </div>
            <div class="stat-card" style="background: var(--bg-secondary); padding: 15px; border-radius: 12px; text-align: center;">
              <div id="admin-total-nu-accounts" style="font-size: 24px; font-weight: bold; color: var(--text-primary);">${stats.total_nu_accounts}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${t("nuAccounts")}</div>
            </div>
            <div class="stat-card" style="background: var(--bg-secondary); padding: 15px; border-radius: 12px; text-align: center;">
              <div id="admin-total-blocked" style="font-size: 24px; font-weight: bold; color: var(--text-primary);">${stats.total_blocked}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${t("blocked")}</div>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">${t("userManagement")}</h2>
          <div class="search-bar" style="margin-bottom: 15px;">
            <input type="text" id="admin-user-search" placeholder="${t("searchByEmail")}" class="auth-input" style="width: 100%;" />
          </div>
          
          <div class="users-list" id="admin-users-list" style="display: flex; flex-direction: column; gap: 10px;">
            ${renderAdminUsersList(users)}
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">${t("connectedGroups")}</h2>
          ${renderConnectedGroupsSection(connectedGroupsPayload)}
        </section>
      </main>
    </div>
  `;
}

export function renderConnectedGroupsSection(payload) {
  const summary = payload?.summary || {};
  const groups = payload?.groups || [];
  const filters = state.adminGroupFilters || {};
  return `
    <div class="connected-groups-summary" style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px;">
      ${renderGroupStat(t("totalGroups"), summary.total_groups, "", "admin-groups-total")}
      ${renderGroupStat(t("active"), summary.active, "active", "admin-groups-active")}
      ${renderGroupStat(t("setupRequired"), summary.setup_required, "setup_required", "admin-groups-setup")}
      ${renderGroupStat(t("missingPermissions"), summary.missing_permissions, "missing_permissions", "admin-groups-permissions")}
    </div>
    <div class="admin-group-controls" style="display: grid; gap: 10px; margin-bottom: 14px;">
      <input type="text" id="admin-group-search" placeholder="${t("searchGroups")}" class="auth-input" style="width: 100%;" />
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        <button type="button" class="filter-chip" data-admin-group-filter-open="status" data-value="${escapeHtml(filters.status || "all")}">
          <span id="admin-group-status-label">${escapeHtml(adminStatusLabel(filters.status || "all"))}</span>
        </button>
        <button type="button" class="filter-chip" data-admin-group-filter-open="sort" data-value="${escapeHtml(filters.sort || "newest")}">
          <span id="admin-group-sort-label">${escapeHtml(adminSortLabel(filters.sort || "newest"))}</span>
        </button>
      </div>
    </div>
    <div id="admin-groups-list" class="connected-groups-list" style="display: flex; flex-direction: column; gap: 10px;">
      ${renderConnectedGroupsList(groups)}
    </div>
  `;
}

function renderGroupStat(label, value, status = "", id = "") {
  return `
    <div class="stat-card" style="background: var(--bg-secondary); border: 1px solid var(--line); padding: 10px 8px; border-radius: 10px; min-width: 0;">
      <div style="display: flex; align-items: center; gap: 6px; font-size: 19px; line-height: 1; font-weight: 800; color: var(--text-primary);">
        <span ${id ? `id="${id}"` : ""}>${Number(value || 0)}</span>
      </div>
      <div style="font-size: 10px; line-height: 1.15; color: var(--text-secondary); margin-top: 5px; overflow-wrap: anywhere;">${escapeHtml(label)}</div>
    </div>
  `;
}

export function renderConnectedGroupsList(groups) {
  if (!groups || groups.length === 0) {
    return `<p style="text-align: center; color: var(--text-secondary);">${escapeHtml(t("noConnectedGroups"))}</p>`;
  }

  return groups.map(group => {
    const title = group.title || group.username || `${t("group")} ${group.telegram_chat_id}`;
    const status = groupStatusMeta(group.status);
    const invite = group.invite_link
      ? `<a href="${escapeHtml(group.invite_link)}" target="_blank" rel="noopener noreferrer" data-admin-group-link style="color: var(--brand); font-weight: 700;">${escapeHtml(t("openGroup"))}</a>`
      : `<span style="color: var(--text-secondary);">${escapeHtml(t("noInviteLink"))}</span>`;
    return `
      <details class="connected-group-card" data-group-id="${escapeHtml(String(group.id))}">
        <summary class="connected-group-summary">
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 10px;">
            <div style="min-width: 0;">
              <div style="font-weight: 800; color: var(--text-primary); overflow-wrap: anywhere;">${escapeHtml(title)}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(String(group.telegram_chat_id))}</div>
            </div>
            <span class="admin-group-status" style="white-space: nowrap; font-size: 11px; font-weight: 800; padding: 5px 9px; border-radius: 999px; color: ${status.color}; background: ${status.bg}; display: inline-flex; align-items: center;">${status.label}</span>
          </div>
          <div style="display: grid; gap: 8px; font-size: 12px; color: var(--text-secondary);">
            <span>${escapeHtml(displayChatType(group.chat_type))}</span>
          </div>
        </summary>
        <div class="connected-group-details" style="display: grid; gap: 8px; font-size: 13px; color: var(--text-secondary);">
          <div><strong style="color: var(--text-primary);">${escapeHtml(t("inviteLink"))}:</strong> ${invite}</div>
          <div><strong style="color: var(--text-primary);">${escapeHtml(t("type"))}:</strong> ${escapeHtml(displayChatType(group.chat_type))}</div>
          <div><strong style="color: var(--text-primary);">${escapeHtml(t("connected"))}:</strong> ${escapeHtml(formatAdminDate(group.connected_at))}</div>
          <div><strong style="color: var(--text-primary);">${escapeHtml(t("lastActivity"))}:</strong> ${escapeHtml(formatAdminDate(group.last_activity_at))}</div>
          <div><strong style="color: var(--text-primary);">${escapeHtml(t("setup"))}:</strong> ${escapeHtml(formatSetupStatus(group.registration_status, group.categories_selected, group.dashboard_message_id))}</div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px;">
            ${permissionPill(t("deleteMessages"), group.permissions?.can_delete_messages)}
            ${permissionPill(t("editMessages"), group.permissions?.can_edit_messages)}
            ${permissionPill(t("pinMessages"), group.permissions?.can_pin_messages)}
          </div>
        </div>
      </details>
    `;
  }).join("");
}

function permissionPill(label, granted) {
  const ok = Boolean(granted);
  const color = ok ? "#12805c" : "#b42318";
  const bg = ok ? "rgba(16,185,129,0.14)" : "rgba(226,85,102,0.14)";
  return `<span style="font-size: 11px; font-weight: 800; padding: 5px 8px; border-radius: 999px; color: ${color}; background: ${bg};">${escapeHtml(label)}</span>`;
}

function groupStatusMeta(status) {
  if (status === "active") {
    return { label: t("active"), color: "#12805c", bg: "rgba(16,185,129,0.14)" };
  }
  if (status === "missing_permissions") {
    return { label: t("missingPermissions"), color: "#9a4f00", bg: "rgba(245,158,11,0.18)" };
  }
  return { label: t("setupRequired"), color: "#8a6a00", bg: "rgba(250,204,21,0.2)" };
}

function displayChatType(value) {
  if (value === "channel") return t("channel");
  return t("group");
}

export function adminStatusLabel(value) {
  if (value === "active") return t("active");
  if (value === "setup_required") return t("setupRequired");
  if (value === "missing_permissions") return t("missingPermissions");
  return t("allStatuses");
}

export function adminSortLabel(value) {
  if (value === "oldest") return t("oldest");
  if (value === "most_active") return t("mostActive");
  return t("newest");
}

function formatSetupStatus(status, categoriesSelected, dashboardMessageId) {
  if (status === "setup_complete" && categoriesSelected && dashboardMessageId) {
    return t("complete");
  }
  if (!categoriesSelected) {
    return t("chooseCategories");
  }
  if (!dashboardMessageId) {
    return t("createDashboard");
  }
  return t("permissionsRequired");
}

function formatAdminDate(value) {
  if (!value) return t("unknown");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("unknown");
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function renderAdminUsersList(users) {
  if (!users || users.length === 0) {
    return `<p style="text-align: center; color: var(--text-secondary);">${escapeHtml(t("noUsersFound"))}.</p>`;
  }

  return users.map(u => {
    const telegramName = [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
    const displayName = formatDisplayName(u.nickname || telegramName || u.username || `Telegram ${u.telegram_id}`, u.email);
    const tgDisplay = u.username 
      ? `<a href="https://t.me/${escapeHtml(u.username)}" target="_blank" style="color: var(--brand); text-decoration: none; font-weight: 500;">@${escapeHtml(u.username)}</a> (${u.telegram_id})`
      : `(${u.telegram_id})`;
    const accountLabel = u.has_nu_account
      ? escapeHtml(u.email)
      : '<span style="color: var(--brand); font-weight: 600;">Telegram only</span>';
    const accountAction = u.role === "admin"
      ? `<span class="admin-user-tag" style="font-size: 12px; color: var(--text-secondary); white-space: nowrap;"></span>`
      : u.has_nu_account
      ? (u.is_blocked
        ? `<button class="admin-btn admin-btn-unblock" data-action="admin-unblock-user" data-email="${escapeHtml(u.email || '')}" data-name="${escapeHtml(displayName)}">${t("unblock")}</button>`
        : `<button class="admin-btn admin-btn-block" data-action="admin-block-user" data-email="${escapeHtml(u.email || '')}" data-name="${escapeHtml(displayName)}">${t("block")}</button>`)
      : `<span class="admin-user-tag" style="font-size: 12px; color: var(--text-secondary); white-space: nowrap;">No NU account</span>`;

    return `
      <div class="user-card" style="background: var(--bg-secondary); padding: 12px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-weight: bold; margin-bottom: 4px;">${escapeHtml(displayName)} ${u.role === 'admin' ? '<span style="color:var(--accent); font-size:10px;">(Admin)</span>' : ''}</div>
          <div style="font-size: 12px; color: var(--text-secondary);">${accountLabel}</div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">${tgDisplay}</div>
          ${u.is_blocked && u.blocked_reason ? `<div style="font-size: 12px; color: var(--red);">Reason: ${escapeHtml(u.blocked_reason)}</div>` : ""}
        </div>
        <div>
          ${accountAction}
        </div>
      </div>
    `;
  }).join("");
}
