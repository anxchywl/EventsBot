import { controls, coverStyle, escapeAttr, escapeHtml, eventRow, status } from "../components/events.js?v=20260529-flicker-fix-v10";
import { formatEventDate, t } from "../i18n.js?v=20260529-flicker-fix-v10";
import { state } from "../state.js";

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

        <!-- Reviews Section -->
        <section class="panel reviews-panel" id="reviews-section-anchor">
          <div class="reviews-header">
            <h2 class="section-title">Reviews (${event.reviews?.length || 0})</h2>
            ${!event.reviews?.find(r => r.is_own) ? `
            <button class="write-review-trigger-btn" id="reviews-pen-trigger" type="button" aria-label="Write a Review">
              <svg viewBox="0 0 24 24" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
            ` : ""}
          </div>
          
          ${renderEventReviewsSummary(event)}

          <!-- Reviews Feed List -->
          <div class="reviews-list-block">
            ${renderEventReviewsList(event)}
          </div>
        </section>

        ${
          event.related_events?.length
            ? `<section class="panel"><h2 class="section-title">${t("related")}</h2>${event.related_events.map(eventRow).join("")}</section>`
            : ""
        }
      </main>

      <!-- Modal Backdrop (Premium App Store Style) -->
      <div class="review-modal-backdrop" id="review-submission-modal">
        <div class="review-modal-card">
          <button class="review-modal-close-btn" id="review-modal-close" type="button" aria-label="Close modal">✕</button>
          ${renderSubmitReviewForm(event)}
        </div>
      </div>
    </div>
  `;
}

function renderEventReviewsSummary(event) {
  const reviews = event.reviews || [];
  const total = reviews.length;
  const sum = reviews.reduce((acc, r) => acc + (r.score || 0), 0);
  const avg = total > 0 ? (sum / total).toFixed(1) : "0.0";
  const counts = {5:0, 4:0, 3:0, 2:0, 1:0};
  reviews.forEach(r => { if (r.score) counts[r.score]++; });

  let barsHtml = '';
  for (let i = 5; i >= 1; i--) {
    const p = total > 0 ? (counts[i] / total) * 100 : 0;
    barsHtml += `
      <div class="rating-bar-row">
        <div class="rating-stars-label">${'★'.repeat(i)}</div>
        <div class="rating-bar-track">
          <div class="rating-bar-fill" style="width: ${p}%"></div>
        </div>
      </div>
    `;
  }

  return `
    <div class="reviews-summary-block">
      <div class="reviews-summary-left">
        <div class="reviews-avg">${avg}</div>
        <div class="reviews-out-of">out of 5</div>
      </div>
      <div class="reviews-summary-right">
        <div class="reviews-bars-container">
          ${barsHtml}
        </div>
      </div>
    </div>
  `;
}

function renderSubmitReviewForm(event) {
  // Check if they already left a review
  const ownReview = event.reviews?.find(r => r.is_own);
  if (ownReview) {
    return ""; // Remove the update form from event details page!
  }

  const isVerified = state.user && state.user.is_verified;
  if (!isVerified) {
    return `
      <form class="review-form unauth-review-form" id="review-verify-btn" style="cursor: pointer;">
        <h3 class="review-form-title">RATE THE EVENT</h3>
        
        <div class="star-rating-selector" style="pointer-events: none;">
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
          <span class="star-btn">★</span>
        </div>

        <div class="form-group" style="pointer-events: none;">
          <textarea class="auth-input review-textarea" readonly placeholder="Share your experience..." style="cursor: pointer;"></textarea>
        </div>
        
        <div class="review-form-actions" style="pointer-events: none;">
          <button class="action primary submit-review-btn" type="button">Submit</button>
        </div>
      </form>
    `;
  }

  return `
    <form id="event-review-form" class="review-form">
      <h3 class="review-form-title">RATE THE EVENT</h3>
      
      <!-- Interactive Stars -->
      <div class="star-rating-selector" data-selected-score="0">
        <span class="star-btn" data-star-score="1" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="2" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="3" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="4" role="button" tabindex="0">★</span>
        <span class="star-btn" data-star-score="5" role="button" tabindex="0">★</span>
        <input type="hidden" id="review-score-field" value="0" />
      </div>

      <div class="form-group">
        <textarea class="auth-input review-textarea" id="review-comment-field" rows="3" placeholder="Share your experience..." maxlength="256"></textarea>
      </div>
      
      <div id="review-error-msg" class="auth-error hide"></div>
      
      <div class="review-form-actions">
        <button class="action primary submit-review-btn" type="submit" disabled>Submit</button>
      </div>
    </form>
  `;
}

function renderEventReviewsList(event) {
  const reviews = event.reviews || [];
  if (reviews.length === 0) {
    return "";
  }

  // Sort own review first, then others by date descending
  const sortedReviews = [...reviews].sort((a, b) => {
    if (a.is_own && !b.is_own) return -1;
    if (!a.is_own && b.is_own) return 1;
    return new Date(b.created_at) - new Date(a.created_at);
  });

  return sortedReviews.map(r => `
    <div class="event-review-card ${r.is_own ? "own-review-card" : ""}">
      <div class="event-review-header">
        <div class="review-meta">
          <strong class="review-nickname">${escapeHtml(r.nickname)}</strong>
          <span class="review-date">${formatReviewDate(r.created_at)}</span>
        </div>
        ${r.score ? `<span class="review-stars">${"★".repeat(r.score)}${"☆".repeat(5 - r.score)}</span>` : ""}
      </div>
      ${r.content ? `<p class="review-body">${escapeHtml(r.content)}</p>` : ""}
    </div>
  `).join("");
}

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
