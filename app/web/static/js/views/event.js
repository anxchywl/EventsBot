import { coverStyle, escapeAttr, escapeHtml, status, formatDisplayName } from "../components/events.js?v=20260608-auth-v7";
import { formatEventDate, t } from "../i18n.js?v=20260608-auth-v7";
import { state } from "../state.js?v=20260608-auth-v7";

// build event meta badges
function meta(label, value, copyable = false) {
  const displayValue = value || "—";
  return `
    <div class="meta ${copyable ? "copyable" : ""}" ${copyable ? `role="button" tabindex="0" data-copy-value="${escapeAttr(displayValue)}" aria-label="${escapeAttr(label)}"` : ""}>
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(displayValue)}</span>
    </div>
  `;
}

// render event details and review sections
export function renderEvent(event) {
  if (!event) {
    return "";
  }
  const isArchived = event.is_archived || event.is_ended;

  return `
    <div class="screen event-screen ${event.is_archived ? "archived" : ""}" data-route="event" data-token="${escapeHtml(event.token)}" data-palette="${escapeHtml(event.palette_key)}">
      <button class="favorite-toggle ${event.is_favorite ? "active" : ""}" type="button" data-action="favorite" aria-label="Favorite">
        <span>★</span>
      </button>
      <header class="cover ${event.cover_url ? "has-cover" : ""}" ${coverStyle(event.cover_url, `event-detail-${event.token || event.title}`)}>
        <h1>${escapeHtml(event.title)}</h1>
      </header>
      <main class="content">
        <section class="panel meta-grid">
          ${meta(t("dateTime"), formatEventDate(event), true)}
          ${meta(t("location"), event.location, true)}
          ${meta(t("organizer"), event.organizer, true)}
          <div class="meta">
            <span class="label">${escapeHtml(t("attendees"))}</span>
            <span class="value" data-attendee-count>${escapeHtml(String(event.attendee_count || 0))}</span>
          </div>
        </section>

        ${event.registration_url ? `<section class="panel action-panel register-panel">
          <button class="action register-action" type="button" data-action="register" ${isArchived ? "disabled" : ""}>${t("register")}</button>
        </section>` : ""}


        <section class="panel">
          <p class="description">${escapeHtml(event.description || "")}</p>
        </section>

        <section class="panel action-panel">
          <div class="event-actions">
            <button class="action" type="button" data-action="reminder" ${isArchived ? "disabled" : ""}>${t("addReminder")}</button>
            <button class="action primary" type="button" data-action="share">${t("share")}</button>
          </div>
        </section>

        <section class="panel reviews-panel" id="reviews-section-anchor">
          <div class="reviews-header">
            <h2 class="section-title">${escapeHtml(t("reviewsSectionTitle"))} (${event.reviews?.length || 0})</h2>
            ${!event.reviews?.find(r => r.is_own) ? `
            <button class="write-review-trigger-btn" id="reviews-pen-trigger" type="button" aria-label="${escapeAttr(t("writeReviewButton"))}">
              <svg viewBox="0 0 24 24" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
            ` : ""}
          </div>
          
          ${renderEventReviewsSummary(event)}

          <div class="reviews-list-block">
            ${renderEventReviewsList(event)}
          </div>
        </section>
      </main>

      <div class="review-modal-backdrop" id="review-submission-modal">
        <div class="review-modal-card">
          <button class="review-modal-close-btn" id="review-modal-close" type="button" aria-label="${escapeAttr(t("close"))}">✕</button>
          ${renderSubmitReviewForm(event)}
        </div>
      </div>
    </div>
  `;
}

// render ratings summary for event details
function renderEventReviewsSummary(event) {
  const reviews = event.reviews || [];
  const ratingTotal = Number(event.rating_count || 0);
  const avg = ratingTotal > 0 && event.average_rating !== null && event.average_rating !== undefined
    ? Number(event.average_rating).toFixed(1)
    : "";
  const counts = {5:0, 4:0, 3:0, 2:0, 1:0};
  reviews.forEach(r => { if (r.score) counts[r.score]++; });

  let barsHtml = '';
  for (let i = 5; i >= 1; i--) {
    const p = ratingTotal > 0 ? (counts[i] / ratingTotal) * 100 : 0;
    barsHtml += `
      <div class="rating-bar-row">
        <div class="rating-stars-label">${'★'.repeat(i)}</div>
        <div class="rating-bar-track">
          <div class="rating-bar-fill" style="width: ${p}%"></div>
        </div>
      </div>
    `;
  }

  if (reviews.length === 0) {
    return `
      <div class="reviews-empty-summary">
        <p>${escapeHtml(t("noReviewsYet"))}</p>
      </div>
    `;
  }

  return `
    <div class="reviews-summary-block">
      <div class="reviews-summary-left">
        <div class="reviews-avg">${avg}</div>
        <div class="reviews-out-of">${escapeHtml(t("ratingOutOf"))}</div>
      </div>
      <div class="reviews-summary-right">
        <div class="reviews-bars-container">
          ${barsHtml}
        </div>
      </div>
    </div>
  `;
}

// render review form for verified users
function renderSubmitReviewForm(event) {
  // hide the form after the user has reviewed
  const ownReview = event.reviews?.find(r => r.is_own);
  if (ownReview) {
    return ""; // keep event details read-only after review submission
  }

  const isVerified = state.user && state.user.is_verified;
  if (!isVerified) {
    return `
      <form class="review-form unauth-review-form" id="review-verify-btn" style="cursor: pointer;">
        <h3 class="review-form-title">${escapeHtml(t("rateTheEvent"))}</h3>
        
        <div class="star-rating-selector" style="pointer-events: none;">
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
        </div>

        <div class="form-group" style="pointer-events: none;">
          <textarea class="auth-input review-textarea" readonly placeholder="${escapeAttr(t("reviewPlaceholder"))}" style="cursor: pointer;"></textarea>
        </div>
        
        <div class="review-form-actions" style="pointer-events: none;">
          <button class="action primary submit-review-btn" type="button">${escapeHtml(t("submitReview"))}</button>
        </div>
      </form>
    `;
  }

  return `
    <form id="event-review-form" class="review-form">
      <h3 class="review-form-title">${escapeHtml(t("rateTheEvent"))}</h3>
      
      <div class="star-rating-selector" data-selected-score="0">
        <span class="star-btn" data-star-score="1" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="2" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="3" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="4" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="5" role="button" tabindex="0">★</span>
        <input type="hidden" id="review-score-field" value="0" />
      </div>

      <div class="form-group">
        <textarea class="auth-input review-textarea" id="review-comment-field" rows="3" placeholder="${escapeAttr(t("reviewPlaceholder"))}" maxlength="256"></textarea>
      </div>
      
      <div id="review-error-msg" class="auth-error hide"></div>
      
      <div class="review-form-actions">
        <button class="action primary submit-review-btn" type="submit" disabled>${escapeHtml(t("submitReview"))}</button>
      </div>
    </form>
  `;
}

// render event reviews with own review first
function renderEventReviewsList(event) {
  const reviews = event.reviews || [];
  if (reviews.length === 0) {
    return "";
  }

  // keep the current user's review visible first
  const sortedReviews = [...reviews].sort((a, b) => {
    if (a.is_own && !b.is_own) return -1;
    if (!a.is_own && b.is_own) return 1;
    return new Date(b.created_at) - new Date(a.created_at);
  });

  return sortedReviews.map(r => `
    <div class="event-review-card ${r.can_delete ? "has-admin-delete" : ""}" data-user-id="${r.user_id}">
      ${r.can_delete ? `
        <button class="admin-review-delete-btn" data-action="admin-delete-review" data-user-id="${escapeAttr(r.user_id)}" aria-label="${escapeAttr(t("deleteReview"))}" title="${escapeAttr(t("deleteReview"))}">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      ` : ""}
      <div class="event-review-main">
        <div class="event-review-header">
          <div class="review-author">
            ${reviewAvatar(r)}
            <div class="review-meta">
              <strong class="review-nickname">${escapeHtml(formatDisplayName(r.nickname))}</strong>
              <span class="review-date">${formatReviewDate(r.created_at)}</span>
            </div>
          </div>
          ${r.score ? `<span class="review-stars">${"★".repeat(r.score)}${"☆".repeat(5 - r.score)}</span>` : ""}
        </div>
        ${r.content ? `<p class="review-body">${escapeHtml(r.content)}</p>` : ""}
      </div>
    </div>
  `).join("");
}

// render review avatar from initials
function reviewAvatar(review) {
  const avatar = review.avatar || {};
  const initials = escapeHtml((avatar.initials || formatDisplayName(review.nickname || "?").slice(0, 2) || "?").slice(0, 2));
  if (avatar.url) {
    return `
      <span class="review-avatar">
        <img src="${escapeAttr(avatar.url)}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex';" />
        <span class="review-avatar-initials" style="display:none;">${initials}</span>
      </span>
    `;
  }
  return `<span class="review-avatar review-avatar-initials">${initials}</span>`;
}

// format review timestamps
function formatReviewDate(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(state.lang, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// render unavailable event state
export function renderEventUnavailable() {
  return `
    <div class="screen">
      <header class="cover compact" ${coverStyle(null, "header-main")}><h1>${t("unavailable")}</h1></header>
      <main class="content">${status(t("unavailable"))}</main>
    </div>
  `;
}

// render event loading state
export function renderEventSkeleton(token) {
  return `
    <div class="screen event-screen skeleton-screen" data-route="event" data-token="${escapeHtml(token)}">
      <button class="favorite-toggle" type="button" disabled aria-label="Favorite">
        <span>★</span>
      </button>
      <header class="cover has-cover" ${coverStyle(null, `event-detail-${token}`)}>
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
