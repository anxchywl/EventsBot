import { controls, coverStyle, escapeAttr, escapeHtml, nav, formatDisplayName } from "../components/events.js?v=20260601-fallback-gradient-v7";
import { t } from "../i18n.js?v=20260601-fallback-gradient-v7";
import { state } from "../state.js";

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
      

      <!-- History Section -->
      <div class="profile-history">
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
    </div>
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
