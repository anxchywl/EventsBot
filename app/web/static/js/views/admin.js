import { escapeHtml, coverStyle, formatDisplayName } from "../components/events.js?v=20260601-fallback-gradient-v7";
import { state, authHeaders } from "../state.js";
import { t } from "../i18n.js?v=20260601-fallback-gradient-v7";
import { authenticate } from "../api.js";

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

export function renderAdminPanel(stats, users) {
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
      </main>
    </div>
  `;
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
    const accountAction = u.has_nu_account
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
