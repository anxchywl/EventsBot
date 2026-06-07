import { controls, coverStyle, escapeAttr, escapeHtml, nav, formatDisplayName } from "../components/events.js?v=20260607-cal-v5";
import { t } from "../i18n.js?v=20260607-cal-v5";
import { state } from "../state.js?v=20260607-cal-v5";

export function renderRatingsTab(profileData = null, reviewsList = []) {
  const feed = state.prefetchedRatings?.feed || reviewsList || [];
  
  return `
    <div class="screen" data-route="ratings">
      <header class="cover compact" ${coverStyle(null, "header-main")}>
        <button class="profile-trigger-btn" id="ratings-profile-trigger" type="button" aria-label="Profile">
          <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        </button>
        <h1>${escapeHtml(t("profile"))}</h1>
      </header>
      <main class="content ratings-content">
        <section class="panel ratings-feed-panel">
          <div class="reviews-feed-list" style="margin-top: 4px;">
            ${renderGlobalReviewsFeed(feed)}
          </div>
        </section>
      </main>
      ${nav("ratings")}
    </div>
  `;
}

export function renderProfileInner() {
  return `
    <div id="auth-profile-container" style="padding-top: 10px;">
      ${renderAuthSection(state.cachedRatingsProfile)}
    </div>
  `;
}

export function renderAuthSection(profileData = null) {
  const isVerified = state.user && state.user.is_verified;
  if (isVerified) return renderProfile(profileData);
  if (state.forgotStep) return renderForgotPasswordCard(state.forgotStep);
  if (state.user?.role === "admin" || state.user?.role === "moderator") {
    return `
      <div class="panel auth-card admin-auth-shortcut">
        <button class="action primary auth-submit-btn admin-auth-shortcut-btn" type="button" data-route="admin">${t("admin")}</button>
      </div>
      ${renderAuthCard()}
    `;
  }
  return renderAuthCard();
}

function renderAuthCard() {
  const mode = state.authMode || "login"; // "login", "verify", "register"
  const email = state.authEmail || "";
  
  if (mode === "verify") {
    const cooldown = state.resendCooldown || 0;
    const code = state.authCode || "";
    return `
      <div class="panel auth-card">
        <h2 class="section-title">${t("verifyEmailTitle")}</h2>
        <p class="description auth-instructions">${t("sentVerificationCode").replace("{email}", `<strong>${escapeHtml(email)}</strong>`)}</p>
        
        <form id="verify-form" class="auth-form">
          <div class="form-group">
            <input class="auth-input code-input" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="6" id="auth-code-field" placeholder="000000" autocomplete="one-time-code" required value="${escapeAttr(code)}" />
          </div>
          <div id="auth-error-msg" class="auth-error ${state.authErrorMsg ? "" : "hide"}">${escapeHtml(state.authErrorMsg || "")}</div>
          <button class="action primary auth-submit-btn" type="submit">${t("verifyCodeBtn")}</button>
        </form>

        <div class="resend-container">
          ${cooldown > 0 
            ? `<span class="resend-timer">${t("resendCooldownText").replace("{cooldown}", cooldown)}</span>` 
            : `<button class="resend-btn" id="resend-code-btn" type="button">${t("resendCodeBtn")}</button>`
          }
        </div>
        <button class="back-to-auth-btn" id="change-email-btn" type="button">${t("changeEmailBtn")}</button>
      </div>
    `;
  }

  const isReg = mode === "register";
  const password = state.authPassword || "";
  const confirmPassword = state.authConfirmPassword || "";
  return `
    <div class="panel auth-card">
      <div class="auth-tabs">
        <button class="auth-tab-btn ${!isReg ? "active" : ""}" id="tab-login-btn" type="button">${t("loginTab")}</button>
        <button class="auth-tab-btn ${isReg ? "active" : ""}" id="tab-register-btn" type="button">${t("registerTab")}</button>
      </div>

      <form id="auth-credentials-form" class="auth-form">
        <div class="form-group">
          <label class="label" for="auth-email-field">${t("corporateEmailLabel")}</label>
          <input class="auth-input" type="email" id="auth-email-field" placeholder="username@nu.edu.kz" maxlength="100" required value="${escapeAttr(email)}" />
        </div>
        <div class="form-group">
          <label class="label" for="auth-password-field">${t("passwordLabel")}</label>
          <div class="input-wrap has-toggle">
            <input class="auth-input" type="${state.authPasswordVisible ? "text" : "password"}" id="auth-password-field" placeholder="••••••••" maxlength="64" required value="${escapeAttr(password)}" />
            <button class="toggle-pass ${state.authPasswordVisible ? "is-visible" : ""}" type="button" data-toggle-for="auth-password-field" aria-label="Toggle password" title="Toggle password">
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>
        ${isReg ? `
        <div class="form-group">
          <label class="label" for="auth-confirm-password-field">${t("confirmPasswordLabel")}</label>
          <input class="auth-input" type="${state.authPasswordVisible ? "text" : "password"}" id="auth-confirm-password-field" placeholder="••••••••" maxlength="64" required value="${escapeAttr(confirmPassword)}" />
        </div>
        ` : `
        <div class="forgot-password-row">
          <button class="forgot-password-btn" id="forgot-password-btn" type="button">${t("forgotPassword")}</button>
        </div>
        `}
        <div id="auth-error-msg" class="auth-error ${state.authErrorMsg ? "" : "hide"}">${escapeHtml(state.authErrorMsg || "")}</div>
        <button class="action primary auth-submit-btn" type="submit">
          ${isReg ? t("makeAccountBtn") : t("enterBtn")}
        </button>
      </form>
    </div>
  `;
}

export function renderForgotPasswordCard(step) {
  const forgotEmail = state.forgotEmail || "";
  const forgotCode = state.forgotCode || "";
  const forgotCooldown = state.forgotResendCooldown || 0;

  if (step === "email") {
    return `
      <div class="panel auth-card">
        <div class="forgot-step-header">
          <button class="forgot-back-btn" id="forgot-back-btn" type="button" aria-label="Go back">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <h2 class="section-title">${t("resetPassword")}</h2>
        </div>
        <form id="forgot-email-form" class="auth-form">
          <div class="form-group">
            <label class="label" for="forgot-email-field">${t("corporateEmailLabel")}</label>
            <input class="auth-input" type="email" id="forgot-email-field" placeholder="username@nu.edu.kz" maxlength="100" required value="${escapeAttr(forgotEmail)}" autocomplete="email" />
          </div>
          <div id="forgot-error-msg" class="auth-error ${state.forgotErrorMsg ? "" : "hide"}">${escapeHtml(state.forgotErrorMsg || "")}</div>
          <div id="forgot-success-msg" class="auth-success hide"></div>
          <button class="action primary auth-submit-btn" type="submit" id="forgot-send-btn">${t("sendCode")}</button>
        </form>
      </div>
    `;
  }

  if (step === "code") {
    return `
      <div class="panel auth-card">
        <div class="forgot-step-header">
          <button class="forgot-back-btn" id="forgot-back-btn" type="button" aria-label="Go back">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <h2 class="section-title">${t("resetPassword")}</h2>
        </div>
        <p class="description auth-instructions">${t("resetCodeSentGeneric")}</p>
        <form id="forgot-code-form" class="auth-form">
          <div class="form-group">
            <input class="auth-input code-input" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="6" id="forgot-code-field" placeholder="000000" autocomplete="one-time-code" required value="${escapeAttr(forgotCode)}" />
          </div>
          <div id="forgot-error-msg" class="auth-error ${state.forgotErrorMsg ? "" : "hide"}">${escapeHtml(state.forgotErrorMsg || "")}</div>
          <button class="action primary auth-submit-btn" type="submit" id="forgot-verify-btn">${t("enterVerificationCode")}</button>
        </form>
        <div class="resend-container">
          ${forgotCooldown > 0
            ? `<span class="resend-timer">${t("resendAvailableIn").replace("{sec}", forgotCooldown)}</span>`
            : `<button class="resend-btn" id="forgot-resend-btn" type="button">${t("resendCode")}</button>`
          }
        </div>
      </div>
    `;
  }

  if (step === "newpwd") {
    return `
      <div class="panel auth-card">
        <div class="forgot-step-header">
          <button class="forgot-back-btn" id="forgot-back-btn" type="button" aria-label="Go back">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <h2 class="section-title">${t("resetPassword")}</h2>
        </div>
        <form id="forgot-reset-form" class="auth-form">
          <div class="form-group">
            <label class="label" for="forgot-newpwd-field">${t("newPassword")}</label>
            <div class="input-wrap has-toggle">
              <input class="auth-input" type="password" id="forgot-newpwd-field" placeholder="••••••••" minlength="8" maxlength="128" required autocomplete="new-password" />
              <button class="toggle-pass" type="button" data-toggle-for="forgot-newpwd-field" aria-label="Toggle password" title="Toggle password">
                <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="form-group">
            <label class="label" for="forgot-confirmpwd-field">${t("confirmPasswordNew")}</label>
            <input class="auth-input" type="password" id="forgot-confirmpwd-field" placeholder="••••••••" minlength="8" maxlength="128" required autocomplete="new-password" />
          </div>
          <div id="forgot-error-msg" class="auth-error ${state.forgotErrorMsg ? "" : "hide"}">${escapeHtml(state.forgotErrorMsg || "")}</div>
          <button class="action primary auth-submit-btn" type="submit" id="forgot-reset-btn">${t("resetPassword")}</button>
        </form>
      </div>
    `;
  }

  return "";
}

function renderProfile(profile) {
  if (!profile) {
    return `
      <div class="panel profile-card skeleton-profile">
        <div class="line skeleton wide"></div>
        <div class="line skeleton"></div>
      </div>
    `;
  }

  return `
    <div class="panel profile-card">
      <div class="profile-header">
        <div class="profile-meta">
          <h2 class="profile-nickname-title">
            <span id="profile-nickname-display">${escapeHtml(formatDisplayName(profile.nickname, profile.email))}</span>
          </h2>
          <span class="profile-email-badge">${escapeHtml(profile.email)}</span>
          ${profile.is_blocked ? `<div style="margin-top: 10px; color: var(--red); font-size: 0.95rem;">Blocked${profile.blocked_reason ? ` (Reason: ${escapeHtml(profile.blocked_reason)})` : ""}</div>` : ""}
          <div id="nickname-error-msg" class="auth-error ${state.nicknameErrorMsg ? "" : "hide"}">${escapeHtml(state.nicknameErrorMsg || "")}</div>
        </div>
        <div class="profile-actions">
        ${(state.user?.role === 'admin' || state.user?.role === 'moderator') ? `
        <button class="profile-admin-icon" id="admin-btn" type="button" data-route="admin" aria-label="${t("admin")}" title="${t("admin")}">
          <span class="profile-admin-label">${t("admin")}</span>
        </button>
        ` : ''}
        <button class="logout-inline-btn" id="logout-btn" type="button" aria-label="${t("logoutBtn")}">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <path d="M16 17l5-5-5-5"></path>
            <path d="M21 12H9"></path>
          </svg>
        </button>
        </div>
      </div>
    </div>
      

    <div class="panel friends-parent-panel">
      ${renderFriendsSubSection()}
      ${renderFriendRequestsSubSection()}
      ${renderFriendSearchSubSection()}
      ${renderPrivacySubSection()}
    </div>

    <!-- History Section -->
    <div class="panel profile-history">
      <h3 class="history-title">${t("myReviewsTitle")}</h3>
      <div class="history-list">
        ${profile.history.length === 0 
          ? `<p class="empty-history-text">${t("emptyHistoryText")}</p>`
          : profile.history.map(item => `
              <article class="history-item" data-event-token="${escapeAttr(item.event_token)}">
                <div class="history-item-header">
                  <strong class="history-event-title">${escapeHtml(item.event_title)}</strong>
                  ${item.score ? `<span class="history-stars">${"★".repeat(item.score)}${"☆".repeat(5 - item.score)}</span>` : ""}
                </div>
                ${item.content ? `<p class="history-comment-content">${escapeHtml(item.content)}</p>` : ""}
                <div class="history-item-footer">
                  <span class="history-date">${formatDate(item.created_at)}</span>
                  <div class="history-actions">
                    <button class="delete-history-btn" data-delete-review-token="${escapeAttr(item.event_token)}">${t("deleteBtn")}</button>
                  </div>
                </div>
              </article>
            `).join("")
        }
      </div>
    </div>
  `;
}

function renderFriendsSubSection() {
  const friends = state.friends?.friends || [];
  if (!friends.length) return "";
  return `
    <div class="friends-sub-section">
      <h3 class="history-title">${escapeHtml(t("friendsTabTitle"))}</h3>
      <div class="friends-list">
        ${friends.map((friend) => renderFriendRow(friend, { mode: "friend" })).join("")}
      </div>
    </div>
  `;
}

function renderFriendRequestsSubSection() {
  const incoming = state.friendRequests?.incoming || [];
  const outgoing = state.friendRequests?.outgoing || [];
  
  if (incoming.length === 0 && outgoing.length === 0) {
    return "";
  }

  return `
    <div class="friends-sub-section">
      <h3 class="history-title">${escapeHtml(t("friendRequestsTitle"))}</h3>
      ${incoming.length ? `
        <div class="request-group">
          <span class="friend-subtitle">${escapeHtml(t("incomingRequests"))}</span>
          ${incoming.map((item) => renderRequestRow(item, "incoming")).join("")}
        </div>
      ` : ""}
      ${outgoing.length ? `
        <div class="request-group">
          <span class="friend-subtitle">${escapeHtml(t("outgoingRequests"))}</span>
          ${outgoing.map((item) => renderRequestRow(item, "outgoing")).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function renderFriendSearchSubSection() {
  const search = state.friendSearch || {};
  
  const inviteOutputHtml = state.currentFriendInvite?.url ? `
    <div class="friend-invite-output" id="friend-invite-output">
      <div class="friend-invite-actions-row">
        <button class="friend-invite-link-btn" type="button" data-copy-value="${escapeAttr(state.currentFriendInvite.url)}">
          <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" style="margin-top: -1px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          ${escapeHtml(t("copyLinkBtn"))}
        </button>
        <button class="action primary friend-share-btn" type="button" data-action="share-invite" data-share-url="${escapeAttr(state.currentFriendInvite.share_url || "")}">${escapeHtml(t("shareBtn"))}</button>
      </div>
    </div>
  ` : "";

  return `
    <div class="friends-sub-section">
      <div class="friends-section-head">
        <h3 class="history-title">${escapeHtml(t("findNuFriendsTitle"))}</h3>
        <button class="action compact-action invite-friend-btn" type="button" data-action="create-friend-invite">${escapeHtml(t("inviteFriendBtn"))}</button>
      </div>
      <div class="friend-search-box">
        <input class="auth-input" id="friend-search-input" type="search" autocomplete="off" maxlength="100" placeholder="${escapeAttr(t("findNuFriendsPlaceholder"))}" value="${escapeAttr(search.query || "")}" />
      </div>
      ${inviteOutputHtml}
      <div id="friend-search-results" class="friends-list">
        ${renderFriendSearchResults()}
      </div>
    </div>
  `;
}

function renderPrivacySubSection() {
  const settings = state.privacySettings || {};
  return `
    <div class="friends-sub-section privacy-sub-section">
      <h3 class="history-title">${escapeHtml(t("privacyTitle"))}</h3>
      ${privacyToggle("show_favorites_to_friends", t("showFavoritesToFriendsLabel"), settings.show_favorites_to_friends !== false)}
      ${privacyToggle("show_profile_to_friends", t("showProfileToFriendsLabel"), settings.show_profile_to_friends !== false)}
      ${privacyToggle("allow_friend_requests", t("allowFriendRequestsLabel"), settings.allow_friend_requests !== false)}
    </div>
  `;
}

function privacyToggle(key, label, checked) {
  return `
    <button class="privacy-toggle" type="button" data-privacy-key="${escapeAttr(key)}" data-checked="${checked ? "true" : "false"}" aria-pressed="${checked ? "true" : "false"}">
      <span>${escapeHtml(label)}</span>
      <span class="privacy-status-label">${checked ? escapeHtml(t("onLabel")) : escapeHtml(t("offLabel"))}</span>
    </button>
  `;
}

function renderRequestRow(item, direction) {
  const friend = item.user || {};
  return `
    <article class="friend-row">
      ${friendAvatar(friend)}
      <div class="friend-main">
        <strong>${escapeHtml(formatDisplayName(friend.nickname, friend.email))}</strong>
        <span>${Number(friend.mutual_friends_count || 0)} ${escapeHtml(t("mutual"))}</span>
      </div>
      <div class="friend-actions-inline">
        ${direction === "incoming" ? `
          <button class="mini-action primary" type="button" data-friend-request-accept="${escapeAttr(item.id)}">${escapeHtml(t("accept"))}</button>
          <button class="mini-action" type="button" data-friend-request-decline="${escapeAttr(item.id)}">${escapeHtml(t("decline"))}</button>
        ` : `
          <button class="mini-action" type="button" data-friend-request-cancel="${escapeAttr(item.id)}">${escapeHtml(t("cancel"))}</button>
        `}
      </div>
    </article>
  `;
}

function renderFriendRow(friend, { mode }) {
  const status = friend.relationship_status || "none";
  const canAdd = mode === "search" && status === "none";
  const pending = status === "outgoing_pending";
  const incoming = status === "incoming_pending";
  return `
    <article class="friend-row ${friend.telegram_url ? "friend-row-clickable" : ""}" data-friend-user-id="${escapeAttr(friend.id)}" ${friend.telegram_url ? `data-open-telegram="${escapeAttr(friend.telegram_url)}"` : ""}>
      ${friendAvatar(friend)}
      <div class="friend-main">
        <strong>${escapeHtml(formatDisplayName(friend.nickname, friend.email))}</strong>
        <span>${Number(friend.friend_count || 0)} ${escapeHtml(t("friends"))} · ${Number(friend.mutual_friends_count || 0)} ${escapeHtml(t("mutual"))}</span>
      </div>
      <div class="friend-actions-inline">
        ${mode === "friend" ? `<button class="mini-action danger" type="button" data-remove-friend="${escapeAttr(friend.id)}">${escapeHtml(t("remove"))}</button>` : ""}
        ${canAdd ? `<button class="mini-action primary" type="button" data-add-friend="${escapeAttr(friend.id)}">${escapeHtml(t("sendFriendRequest"))}</button>` : ""}
        ${pending ? `<span class="friend-status-pill">${escapeHtml(t("requestSent"))}</span>` : ""}
        ${incoming ? `<span class="friend-status-pill">${escapeHtml(t("incomingRequests"))}</span>` : ""}
      </div>
    </article>
  `;
}

function friendAvatar(friend) {
  const avatar = friend.avatar || {};
  const initials = escapeHtml(avatar.initials || "NU");
  if (avatar.url) {
    return `
      <div style="position: relative; width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
        <img class="friend-avatar" src="${escapeAttr(avatar.url)}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex';" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 50%; object-fit: cover;" />
        <span class="friend-avatar initials" style="display: none; width: 100%; height: 100%;">${initials}</span>
      </div>
    `;
  }
  return `<span class="friend-avatar initials">${initials}</span>`;
}

export function renderFriendSearchResults() {
  const search = state.friendSearch || {};
  const results = search.results || [];
  return `
    ${search.loading ? `<div class="line skeleton"></div>` : ""}
    ${search.query && (search.query || "").length >= 2 && !results.length && !search.loading ? `<p class="empty-history-text">${escapeHtml(t("noVerifiedUsersFound"))}</p>` : ""}
    ${results.map((friend) => renderFriendRow(friend, { mode: "search" })).join("")}
    ${search.hasMore ? `<button class="action compact-action full-width" type="button" data-action="friend-search-more">Load more</button>` : ""}
  `;
}

function renderGlobalReviewsFeed(reviews) {
  if (!reviews || reviews.length === 0) {
    return `
      <div class="empty-reviews-state">
        <p class="empty-reviews-text">${t("emptyGlobalFeedText")}</p>
      </div>
    `;
  }

  return reviews.map(review => `
    <article class="feed-review-card">
      <div class="feed-review-header">
        <div class="feed-review-meta">
          <strong class="feed-review-nickname">${escapeHtml(formatDisplayName(review.nickname, review.email))}</strong>
          <span class="feed-review-event-link" data-event-token="${escapeAttr(review.event_token)}">${t("onWord")} ${escapeHtml(review.event_title)}</span>
        </div>
        <div class="feed-review-actions">
          ${review.score ? `<span class="feed-review-stars">${"★".repeat(review.score)}</span>` : ""}
          ${state.user && (state.user.role === 'admin' || state.user.role === 'moderator') ? `
            <button class="admin-delete-review-btn" data-event-token="${escapeAttr(review.event_token)}" data-admin-delete-review="${escapeAttr(review.user_id)}" title="${t("deleteBtn")}">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          ` : ''}
        </div>
      </div>
      ${review.content ? `<p class="feed-review-body">${escapeHtml(review.content)}</p>` : ""}
      <span class="feed-review-date">${formatDate(review.created_at)}</span>
    </article>
  `).join("");
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(state.lang, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
