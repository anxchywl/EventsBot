import {
  addFavorite,
  authenticate,
  createReminder,
  deleteReminder,
  fetchEvent,
  fetchEventFilters,
  fetchEvents,
  fetchReminders,
  registerEvent,
  removeFavorite,
  shareEvent,
  register,
  verifyCode,
  resendCode,
  login,
  fetchProfile,
  updateNickname,
  logout,
  submitReview,
  deleteReview,
  fetchReviews,
  request,
  forgotPasswordRequest,
  forgotPasswordVerify,
  forgotPasswordReset,
} from "./api.js";
import { loadingScreen, resetFallbackCoverStyles, startCountdowns } from "./components/events.js?v=20260529-flicker-fix-v10";
import { closeFilterSheet, openFilterSheet } from "./components/filterSheet.js?v=20260529-flicker-fix-v10";
import { closeSheet, openReminderSheet } from "./components/sheets.js?v=20260529-flicker-fix-v10";
import { t, translateError } from "./i18n.js?v=20260529-flicker-fix-v10";
import { currentTheme, nextLang, normalizeEventFilters, rememberScroll, restoreScroll, setEventFilters, setLang, setTheme, state, toggleTheme } from "./state.js";
import { configureBackButton, haptic, initTelegram, openLink, openTelegramLink, startParam, tg } from "./telegram.js";
import { renderEvent, renderEventUnavailable, renderEventSkeleton } from "./views/event.js?v=20260529-flicker-fix-v10";
import { renderEventResults, renderFilterBar, renderMenu, renderPlaceholder } from "./views/menu.js?v=20260529-flicker-fix-v10";
import { renderReminders } from "./views/reminders.js?v=20260529-flicker-fix-v10";
import { renderCalendarInner, attachCalendarInteractions, refreshCalendarMonthPanels } from "./views/calendar.js?v=20260529-flicker-fix-v10";
import { renderAuthSection, renderRatingsTab, renderForgotPasswordCard } from "./views/ratings.js?v=20260529-flicker-fix-v10";


const app = document.getElementById("app");
let backHandler = async () => {
  // Always navigate to events menu, bypassing early return checks
  if (state.route === "events" && state.token === "") {
    return; // Already on events menu, no need to navigate
  }
  try {
    await navigate("events", { direction: "back", quiet: false });
  } catch (error) {
    console.error("Back button navigation failed:", error);
    // Force fallback navigation
    state.route = "events";
    state.token = "";
    state.calendarMode = false;
    document.documentElement.setAttribute("data-current-route", "events");
    await renderCurrent({ quiet: false });
  }
};
let eventFetchTimer = null;
let searchCloseTimer = null;
const favoriteRequests = new Set();
let pendingEventsRefreshAfterFavorite = false;
let lastDirectHapticAt = 0;

// Snapshot of the events menu DOM — saved when leaving for an event page,
// restored instantly when coming back so the transition is invisible.
let cachedMenuHTML = null;


export async function boot() {
  setLang(state.lang);
  setTheme(state.theme || currentTheme());

  const initialRoute = routeFromLocation();
  if (initialRoute.route === "event" || initialRoute.route === "calendar") {
    app.innerHTML = loadingScreen();
    document.documentElement.setAttribute("data-current-route", initialRoute.route);
  } else {
    document.documentElement.setAttribute("data-current-route", state.route);
  }

  initTelegram(() => {
    resetFallbackCoverStyles();
    if (initialRoute.route === "events") {
      renderCurrent();
    }
  });
  await authenticate().catch(() => null);
  window.addEventListener("hashchange", () => loadFromLocation());
  document.addEventListener("pointerdown", onPointerDown, { passive: true });
  document.addEventListener("touchstart", onPointerDown, { passive: true });
  document.addEventListener("click", onClick);
  app.addEventListener("input", onInput);
  app.addEventListener("focusin", (e) => {
    if (e.target.closest("#auth-profile-container input")) {
      document.documentElement.classList.add("auth-focusing");
    }
  });
  app.addEventListener("focusout", (e) => {
    onFocusOut(e);
    if (e.target.closest("#auth-profile-container input")) {
      // Small timeout to allow focus to transfer to another input without flickering the nav bar
      setTimeout(() => {
        if (!document.activeElement || !document.activeElement.closest("#auth-profile-container input")) {
          document.documentElement.classList.remove("auth-focusing");
        }
      }, 50);
    }
  });
  installKeyboardOverlayNav();
  loadFromLocation();
}

function installKeyboardOverlayNav() {
  const viewport = window.visualViewport;
  if (!viewport) {
    return;
  }
  let stableViewportHeight = Math.max(
    window.innerHeight || 0,
    document.documentElement.clientHeight || 0,
    viewport.height || 0,
  );
  const updateKeyboardOffset = () => {
    stableViewportHeight = Math.max(
      stableViewportHeight,
      window.innerHeight || 0,
      document.documentElement.clientHeight || 0,
      viewport.height || 0,
    );
    const offset = Math.max(
      0,
      stableViewportHeight - viewport.height - viewport.offsetTop,
    );
    document.documentElement.style.setProperty("--keyboard-cover-offset", `${Math.round(offset)}px`);
  };
  viewport.addEventListener("resize", updateKeyboardOffset);
  viewport.addEventListener("scroll", updateKeyboardOffset);
  updateKeyboardOffset();
}

function routeFromLocation() {
  const pathEvent = window.location.pathname.match(/^\/events\/([^/]+)/);
  if (pathEvent) {
    return { route: "event", token: decodeURIComponent(pathEvent[1]) };
  }
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [hashRoute, hashQuery = ""] = hash.split("?");
  const filterParams = new URLSearchParams(hashQuery);
  if (!hashRoute || hashRoute === "events") {
    hydrateFiltersFromParams(filterParams);
    return { route: "events", token: "" };
  }
  if (hashRoute.startsWith("events/")) {
    return { route: "event", token: decodeURIComponent(hashRoute.split("/")[1] || "") };
  }
  if (hashRoute === "favorites") {
    setEventFilters({ ...state.eventFilters, favoritesOnly: true });
    return { route: "events", token: "" };
  }
  if (hashRoute === "reminders") {
    return { route: "events", token: "" };
  }
  if (hashRoute === "ratings") {
    return { route: "events", token: "" };
  }
  if (hashRoute === "calendar") {
    return { route: "calendar", token: "" };
  }
  const start = startParam() || new URLSearchParams(window.location.search).get("startapp") || "";
  if (start.startsWith("event_")) {
    return { route: "event", token: start.slice(6) };
  }
  return { route: "events", token: "" };
}

async function loadFromLocation() {
  const next = routeFromLocation();
  await navigate(next.route, { token: next.token, replaceHash: false });
}

async function navigate(route, options = {}) {
  if (route === state.route && (options.token || "") === state.token && options.replaceHash !== false) {
    return;
  }
  rememberScroll(state.route);

  const prevRoute = state.route;
  const targetRoute = route;

  // Pre-fetch data for the next route BEFORE starting the view transition.
  // This ensures the DOM swap inside startViewTransition is near-instant,
  // preventing a visual gap where the old page has exited but the new one
  // hasn't yet appeared (caused by awaiting a network request inside the callback).
  let prefetchedEvent = null;
  let prefetchedReminders = null;
  let prefetchedEvents = null;
  let shouldRefreshEventsAfterNavigation = false;

  // Going events → event: snapshot the current menu DOM for instant restore later.
  // Only save if the DOM actually has a fully-rendered events screen (not a loading screen).
  if (prevRoute === "events" && route === "event") {
    const eventsScreen = app.querySelector('[data-route="events"]');
    if (eventsScreen) {
      cachedMenuHTML = app.innerHTML.replace(/\snav-hidden\b/g, "");
    }
  }

  // Going back event → events: restore from snapshot — no fetch, no re-render.
  const restoringFromCache = prevRoute === "event" && route === "events" && cachedMenuHTML !== null;

  const returningFromEventWithLocalEvents = prevRoute === "event" && route === "events" && state.events.length > 0;

  if (!restoringFromCache) {
    try {
      if (route === "event") {
        const token = options.token || "";
        if (token) {
          prefetchedEvent = await fetchEvent(token);
        }
      } else if (route === "events") {
        await ensureEventFilterOptions();
        if (returningFromEventWithLocalEvents) {
          prefetchedEvents = state.events;
          shouldRefreshEventsAfterNavigation = true;
        } else {
          prefetchedEvents = await fetchEvents(state.eventFilters);
        }
      } else if (route === "calendar") {
        await ensureEventFilterOptions();
        prefetchedEvents = await fetchEvents({ ...state.eventFilters, relevance: "all" });
      }
    } catch (_) {
      // Pre-fetch failed — renderRoute will handle the error gracefully
    }
  }

  const performNavigation = async () => {
    state.route = route;
    state.token = options.token || "";
    if (route === "calendar") {
      state.calendarMode = true;
    } else if (route === "events") {
      state.calendarMode = false;
    }
    // Update HTML element's data attribute for CSS-based visibility control
    document.documentElement.setAttribute("data-current-route", route);
    if (route !== "events" && route !== "calendar") {
      window.clearTimeout(searchCloseTimer);
      state.eventSearch.active = false;
      state.eventSearch.query = "";
      document.documentElement.classList.remove("event-searching", "event-search-closing");
    }
    // Show back button on all routes except main events/calendar views
    // Back button always navigates to events menu
    const isMainView = route === "events" || route === "calendar";
    configureBackButton(!isMainView, backHandler);

    if (restoringFromCache) {
      // Restore the events menu DOM from cache — synchronous, no network, no flicker.
      // Inject `no-enter` into the HTML string BEFORE parsing so CSS animations
      // (slideDown, slideUp, eventListRise, etc.) never fire on the restored nodes.
      suppressNavScroll = true;
      if (!app) {
        console.error("App element not found during cache restoration");
        throw new Error("App element not found");
      }
      
      // Validate cached menu exists and contains a screen element
      if (!cachedMenuHTML || !cachedMenuHTML.includes('<div class="screen')) {
        console.warn("Cached menu HTML is invalid, forcing fresh render");
        restoringFromCache = false;
        cachedMenuHTML = null;
        // Fall through to normal rendering below
      } else {
        app.innerHTML = cachedMenuHTML.replace(/(<div class="screen)/, '$1 no-enter');

        restoreScroll(route);
        requestAnimationFrame(() => {
          lastScrollY = window.scrollY;
          requestAnimationFrame(() => {
            lastScrollY = window.scrollY;
            suppressNavScroll = false;
          });
        });

        if (options.replaceHash !== false) {
          syncHash(route, state.token);
        }
        startCountdowns(app);
        if (state.calendarMode) {
          refreshCalendarMonthPanels({ forceVisible: true });
          attachCalendarInteractions();
        }
        return;
      }
    }

    // Normal rendering (not from cache, or cache was invalid)
    // Inject pre-fetched data into state so renderRoute skips the network call
    if (prefetchedEvent !== null) {
      state.currentEvent = prefetchedEvent;
    } else if (prefetchedEvents !== null) {
      state.events = prefetchedEvents;
    }
    await renderRoute({ quiet: options.quiet ?? isTopLevelRoute(route), prefetched: true });
    if (options.keepScroll) {
      // Do not reset scroll
    } else if (route === "events" || route === "calendar") {
      restoreScroll(route);
    } else {
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    if (options.replaceHash !== false) {
      syncHash(route, state.token);
    }
    if (shouldRefreshEventsAfterNavigation) {
      refreshEventsAfterNavigation();
    }
  };

  const isBack = options.direction === "back" ||
    (isTopLevelRoute(prevRoute) && isTopLevelRoute(targetRoute) && getRouteIndex(targetRoute) < getRouteIndex(prevRoute));

  // When restoring from cache, skip the View Transitions API entirely.
  // startViewTransition hides the real DOM during its animation and replaces it
  // with pseudo-element snapshots — when animation ends the real DOM re-appears,
  // causing the visible flash on date/section panels. A direct synchronous swap is
  // completely invisible to the user.
  if (restoringFromCache) {
    await performNavigation();
    
    // Sync badges from state.events to the restored cached DOM instantly
    state.events.forEach(item => setEventRowFavoriteBadge(item.token, item.is_favorite));
    
    // If in favoritesOnly mode, remove rows that are no longer favorites
    if (state.eventFilters.favoritesOnly) {
      app.querySelectorAll("[data-event-token]").forEach((row) => {
        const token = row.dataset.eventToken;
        const eventItem = state.events.find(e => e.token === token);
        if (eventItem && !eventItem.is_favorite) {
          row.remove();
        }
      });
    }

    return;
  }

  if (options.circularEvent && document.startViewTransition) {
    const event = options.circularEvent;
    const x = event.clientX || window.innerWidth / 2;
    const y = event.clientY || window.innerHeight / 2;
    const endRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y),
    );

    document.documentElement.classList.add("theme-transitioning");

    const transition = document.startViewTransition(async () => {
      document.documentElement.classList.add("no-transitions");
      await performNavigation();
    });

    transition.ready.then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${endRadius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: 450,
          easing: "cubic-bezier(0.4, 0, 0.2, 1)",
          pseudoElement: "::view-transition-new(root)",
        },
      );
    });

    try {
      await transition.finished;
    } finally {
      document.documentElement.classList.remove("theme-transitioning");
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          document.documentElement.classList.remove("no-transitions");
        });
      });
    }
    return;
  }

  if (!document.startViewTransition) {
    await performNavigation();
    const contentEl = app.querySelector(".content");
    if (contentEl) {
      contentEl.classList.remove("page-enter-forward", "page-enter-back");
      const screenEl = app.querySelector(".screen");
      if (screenEl) {
        screenEl.classList.remove("no-enter");
      }
      void contentEl.offsetWidth;
      if (isBack) {
        contentEl.classList.add("page-enter-back");
      } else {
        contentEl.classList.add("page-enter-forward");
      }
    }
    return;
  }

  document.documentElement.classList.add("page-transitioning");
  if (isBack) {
    document.documentElement.setAttribute("data-nav-direction", "back");
  } else {
    document.documentElement.removeAttribute("data-nav-direction");
  }

  const transition = document.startViewTransition(async () => {
    try {
      await performNavigation();
    } catch (error) {
      console.error("Error during navigation:", error);
      // Attempt to at least update the route attribute even if something failed
      document.documentElement.setAttribute("data-current-route", route);
    }
  });

  try {
    await transition.finished;
  } catch (error) {
    console.error("View transition error:", error);
  } finally {
    document.documentElement.classList.remove("page-transitioning");
    document.documentElement.removeAttribute("data-nav-direction");
    document.documentElement.classList.remove("full-page-transition");
  }
}

function getRouteIndex(route) {
  const order = ["events", "calendar", "ratings", "reminders"];
  return order.indexOf(route);
}

async function renderRoute({ quiet = false, prefetched = false } = {}) {
  // If data was pre-fetched before the view transition, skip loading screen & network calls
  // so the DOM swap is synchronous and the animation is perfectly smooth.
  const useCache = prefetched &&
    ((state.route === "event" && state.currentEvent !== undefined) ||
      (state.route === "reminders" && state.reminders !== undefined) ||
      (state.route === "ratings" && state.prefetchedRatings !== undefined) ||
      ((state.route === "events" || state.route === "calendar") && state.events !== undefined && state.events !== null && state.events.length > 0));

  if (!quiet && !useCache) {
    app.innerHTML = loadingScreen();
  }
  try {
    if (state.route === "event") {
      if (!state.token) {
        state.currentEvent = null;
        app.innerHTML = renderEventUnavailable();
        applyQuietRender(quiet);
        return;
      }
      if (!useCache) {
        // Optimistically render skeleton if we don't have the event yet
        if (!quiet) {
          app.innerHTML = renderEventSkeleton(state.token);
        }
        state.currentEvent = await fetchEvent(state.token);
      }
      app.innerHTML = renderEvent(state.currentEvent);
      applyQuietRender(quiet);
      initEventReviewsHandlers();
      return;
    }
    if (!useCache) {
      await ensureEventFilterOptions();
      const fetchFilters = state.route === "calendar" ? { ...state.eventFilters, relevance: "all" } : state.eventFilters;
      state.events = await fetchEvents(fetchFilters);
    }
    if (!state.events || state.events.length === 0) {
      console.warn("No events to render, but continuing with empty array");
    }
    app.innerHTML = renderMenu(state.events || []);
    applyQuietRender(quiet);
    initRatingsHandlers();
    if (state.calendarMode) attachCalendarInteractions();
  } catch (error) {
    console.error("Error during route rendering:", state.route, error);
    if (state.route === "event" && error.status === 404) {
      app.innerHTML = renderEventUnavailable();
      applyQuietRender(quiet);
      return;
    }
    app.innerHTML = renderPlaceholder(state.route);
    applyQuietRender(quiet);
  }
}

function renderCurrent({ quiet = false } = {}) {
  const filterBar = app.querySelector(".filter-bar");
  const filterScroll = filterBar ? filterBar.scrollLeft : 0;

  if (state.route === "event") {
    renderEventPreservingFavorite();
    applyQuietRender(quiet);
    return;
  }
  app.innerHTML = renderMenu(state.events);
  applyQuietRender(quiet);
  initRatingsHandlers();
  if (state.calendarMode) attachCalendarInteractions();

  if (filterScroll) {
    const newFilterBar = app.querySelector(".filter-bar");
    if (newFilterBar) {
      newFilterBar.scrollLeft = filterScroll;
    }
  }
}

function applyQuietRender(quiet) {
  if (!quiet) {
    startCountdowns(app);
    return;
  }
  app.firstElementChild?.classList.add("no-enter");
  startCountdowns(app);
}

function syncHash(route, token) {
  const target = route === "events" ? eventsHash() : route === "event" ? `#/events/${token}` : `#/${route}`;
  if (window.location.hash !== target) {
    history.pushState(null, "", target);
  }
}

function renderEventPreservingFavorite() {
  // Snapshot the current favorite button's visual state before re-render.
  const currentButton = app.querySelector(".event-screen [data-action='favorite']");
  const wasFavorite = currentButton
    ? currentButton.classList.contains("active")
    : Boolean(state.currentEvent?.is_favorite);

  // Re-render the event HTML.
  app.innerHTML = renderEvent(state.currentEvent);

  // Patch the freshly-created button in-place — never move detached DOM nodes
  // back into the tree, which can fire color transitions when no-transitions is lifted.
  const nextButton = app.querySelector(".event-screen [data-action='favorite']");
  if (nextButton) {
    nextButton.classList.toggle("active", wasFavorite);
    nextButton.classList.remove("favorite-spin", "favorite-unspin", "is-loading");
    nextButton.disabled = false;
  }

  initEventReviewsHandlers();
}

function eventsHash() {
  const params = new URLSearchParams();
  const filters = state.eventFilters;
  if (filters.sort && filters.sort !== "time_asc") params.set("sort", filters.sort);
  if (filters.relevance && filters.relevance !== "active") params.set("rel", filters.relevance);
  if (filters.categories.length) params.set("cat", filters.categories.join(","));
  if (filters.organizers.length) params.set("org", filters.organizers.join(","));
  if (filters.locations.length) params.set("loc", filters.locations.join(","));
  if (filters.timeOfDay?.length) params.set("tod", filters.timeOfDay.join(","));
  if (filters.favoritesOnly) params.set("fav", "1");
  const query = params.toString();
  return query ? `#/?${query}` : "#/";
}

function hydrateFiltersFromParams(params) {
  if (![...params.keys()].length) {
    return;
  }
  setEventFilters(normalizeEventFilters({
    ...state.eventFilters,
    sort: params.get("sort") || state.eventFilters.sort,
    relevance: params.get("rel") || state.eventFilters.relevance,
    categories: splitParam(params.get("cat")),
    organizers: splitParam(params.get("org")),
    locations: splitParam(params.get("loc")),
    timeOfDay: splitParam(params.get("tod")),
    favoritesOnly: params.get("fav") === "1",
  }));
}

function splitParam(value) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

async function ensureEventFilterOptions() {
  if (state.eventFilterOptionsLoaded) {
    return;
  }
  const options = await fetchEventFilters();
  state.eventFilterOptions = {
    categories: Array.isArray(options.categories) ? options.categories : [],
    organizers: Array.isArray(options.organizers) ? options.organizers : [],
    locations: Array.isArray(options.locations) ? options.locations : [],
  };
  state.eventFilterOptionsLoaded = true;
}

function updateEventFilters(patch) {
  setEventFilters({ ...state.eventFilters, ...patch });
  cachedMenuHTML = null;
  syncHash("events", "");
  patchEventsFilterBar();
  
  if (state.route === "calendar") {
    window.clearTimeout(eventFetchTimer);
    eventFetchTimer = window.setTimeout(async () => {
      try {
        state.events = await fetchEvents(state.eventFilters);
        refreshCalendarMonthPanels();
      } catch {
        haptic("error");
      }
    }, 180);
    return;
  }
  
  const region = app.querySelector("[data-events-list-region]");
  if (region) {
    region.classList.add("events-list-loading");
  }

  window.clearTimeout(eventFetchTimer);
  eventFetchTimer = window.setTimeout(async () => {
    try {
      state.events = await fetchEvents(state.eventFilters);
      if (region) region.classList.remove("events-list-loading");
      patchEventsList({ animate: true });
    } catch {
      if (region) region.classList.remove("events-list-loading");
      haptic("error");
    }
  }, 180);
}

function refreshEventsAfterNavigation() {
  if (favoriteRequests.size) {
    pendingEventsRefreshAfterFavorite = true;
    return;
  }
  refreshEventsList({ animate: true });
}

async function refreshEventsList({ animate = false } = {}) {
  if (state.route !== "events" && state.route !== "calendar") {
    return;
  }
  try {
    const fetchFilters = state.route === "calendar" ? { ...state.eventFilters, relevance: "all" } : state.eventFilters;
    state.events = await fetchEvents(fetchFilters);
    if (state.route === "events") patchEventsList({ quiet: true, animate });
    if (state.route === "calendar") {
        refreshCalendarMonthPanels();
    }
  } catch {
    haptic("error");
  }
}

function openEventSearch() {
  window.clearTimeout(searchCloseTimer);
  state.eventSearch.active = true;
  document.documentElement.classList.remove("event-search-closing");
  document.documentElement.classList.add("event-searching");
  patchEventsFilterBar();
  requestAnimationFrame(() => {
    const input = app.querySelector("[data-event-search-input]");
    input?.focus({ preventScroll: true });
    input?.select?.();
  });
}

function closeEventSearch() {
  state.eventSearch.active = false;
  state.eventSearch.query = "";
  document.documentElement.classList.add("event-search-closing");
  patchEventsFilterBar();
  patchEventsList({ quiet: true });
  window.clearTimeout(searchCloseTimer);
  searchCloseTimer = window.setTimeout(() => {
    document.documentElement.classList.remove("event-searching", "event-search-closing");
  }, 340);
}

function patchEventsFilterBar() {
  const current = app.querySelector(".filter-bar-shell");
  if (current) {
    const filterBar = current.querySelector(".filter-bar");
    const filterScroll = filterBar ? filterBar.scrollLeft : 0;
    current.outerHTML = renderFilterBar();
    if (filterScroll) {
      const newFilterBar = app.querySelector(".filter-bar");
      if (newFilterBar) {
        newFilterBar.scrollLeft = filterScroll;
      }
    }
  }
}

function patchEventsList({ quiet = false, animate = false } = {}) {
  const region = app.querySelector("[data-events-list-region]");
  if (!region) {
    renderCurrent({ quiet: true });
    return;
  }
  const screen = app.firstElementChild;
  if (quiet) {
    screen?.classList.add("no-enter");
  }
  const newHTML = renderEventResults(state.events);
  if (region.innerHTML === newHTML) {
    return;
  }
  region.innerHTML = newHTML;
  if (animate) {
    region.classList.remove("events-list-soft-update");
    void region.offsetWidth;
    region.classList.add("events-list-soft-update");
  }
  startCountdowns(app);
}

function onPointerDown(event) {
  if (!event.target.closest("[data-action='theme'], [data-action='lang'], [data-action='reminder'], [data-action='share']")) {
    return;
  }
  lastDirectHapticAt = Date.now();
  haptic("impact");
}

function hapticImpactFallback() {
  if (Date.now() - lastDirectHapticAt > 260) {
    haptic("impact");
  }
}

async function onClick(event) {
  const theme = event.target.closest("[data-action='theme']");
  if (theme) {
    triggerControlAnimation(theme, "theme-switching");
    hapticImpactFallback();
    runCircularTransition(event, () => {
      resetFallbackCoverStyles();
      toggleTheme();
      renderCurrent({ quiet: true });
    });
    return;
  }
  const lang = event.target.closest("[data-action='lang']");
  if (lang) {
    hapticImpactFallback();
    runCircularTransition(event, () => {
      nextLang();
      renderCurrent({ quiet: true });
    });
    return;
  }
  const reminderRemove = event.target.closest("[data-reminder-id]");
  if (reminderRemove) {
    await deleteReminder(reminderRemove.dataset.reminderId);
    haptic("success");
    await navigate("reminders", { replaceHash: false, quiet: true });
    return;
  }
  const filterOpen = event.target.closest("[data-filter-open]");
  if (filterOpen) {
    await ensureEventFilterOptions();
    openFilterSheet({
      type: filterOpen.dataset.filterOpen,
      onChange: updateEventFilters,
    });
    return;
  }
  const searchOpen = event.target.closest("[data-action='event-search-open']");
  if (searchOpen) {
    openEventSearch();
    haptic();
    return;
  }
  const calendarToggle = event.target.closest("[data-action='calendar-toggle']");
  if (calendarToggle) {
    haptic("light");
    const nextRoute = state.calendarMode ? "events" : "calendar";
    navigate(nextRoute, { circularEvent: event });
    return;
  }
  const searchClose = event.target.closest("[data-action='event-search-close']");
  if (searchClose) {
    closeEventSearch();
    haptic();
    return;
  }
  const copyTarget = event.target.closest("[data-copy-value]");
  if (copyTarget) {
    await copyText(copyTarget.dataset.copyValue || "");
    copyTarget.classList.add("copied");
    window.setTimeout(() => copyTarget.classList.remove("copied"), 520);
    haptic("success");
    return;
  }
  const favoriteFilter = event.target.closest("[data-action='favorite-filter-toggle']");
  if (favoriteFilter) {
    updateEventFilters({ favoritesOnly: !state.eventFilters.favoritesOnly });
    return;
  }
  const favoriteRemove = event.target.closest("[data-favorite-remove]");
  if (favoriteRemove) {
    const token = favoriteRemove.dataset.favoriteRemove;
    if (favoriteRequests.has(token)) return;
    favoriteRequests.add(token);
    favoriteRemove.disabled = true;
    
    // Optimistic UI update
    const eventItem = state.events.find((item) => item.token === token);
    if (eventItem) {
      eventItem.is_favorite = false;
      syncFavoriteState(token, false);
      if (state.eventFilters.favoritesOnly) {
        state.events = state.events.filter((item) => item.token !== token);
        patchEventsList({ quiet: true, animate: true });
      } else {
        setEventRowFavoriteBadge(token, false);
      }
    }
    
    try {
      await removeFavorite(token);
      haptic("success");
    } catch {
      if (eventItem) {
        eventItem.is_favorite = true;
        syncFavoriteState(token, true);
      }
      favoriteRemove.disabled = false;
      haptic("error");
    } finally {
      favoriteRequests.delete(token);
    }
    return;
  }
  const row = event.target.closest("[data-event-token]");
  if (row) {
    const isHistoryItem = Boolean(row.closest(".history-item"));
    if (isHistoryItem) {
      closeAuthSheet();
    }
    document.querySelector(".app-nav")?.classList.add("nav-hidden");
    await navigate("event", {
      token: row.dataset.eventToken,
      quiet: true,
    });
    return;
  } const route = event.target.closest("button[data-route]");
  if (route) {
    const parentNav = route.closest(".app-nav");
    if (parentNav) {
      parentNav.querySelectorAll("button[data-route]").forEach(btn => btn.classList.remove("active"));
      route.classList.add("active");
    }
    await navigate(route.dataset.route, { quiet: true });
    return;
  }

  const action = event.target.closest("[data-action]");
  if (action) {
    await handleEventAction(action.dataset.action, action);
    return;
  }
}

function triggerControlAnimation(element, className) {
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
  window.setTimeout(() => element.classList.remove(className), 520);
}

function onInput(event) {
  const searchInput = event.target.closest("[data-event-search-input]");
  if (!searchInput) {
    return;
  }
  // Sanitize in real-time (max 100 length, no SQL/script chars, no extra spaces)
  let val = searchInput.value.slice(0, 100).replace(/[<>&"'/`\\;]/g, "");
  val = val.replace(/^\s+/, "").replace(/\s{2,}/g, " ");
  searchInput.value = val;
  state.eventSearch.query = val;
  patchEventsList({ quiet: true });
}

function onFocusOut(event) {
  const searchInput = event.target.closest("[data-event-search-input]");
  if (searchInput) {
    const val = searchInput.value.trim();
    if (searchInput.value !== val) {
      searchInput.value = val;
      state.eventSearch.query = val;
      patchEventsList({ quiet: true });
    }
  }
}

async function handleEventAction(action, element) {
  const event = state.currentEvent;
  if (!event) return;
  if (action === "favorite") {
    await toggleFavorite(event);
  }
  if (action === "reminder") {
    hapticImpactFallback();
    openReminderSheet({
      event: state.currentEvent,
      onSubmit: async (offset, deletedReminderIds = []) => {
        for (const reminderId of deletedReminderIds) {
          await deleteReminder(reminderId);
        }
        if (offset) {
          await createReminder(event.token, offset);
        }
        haptic("success");
        try {
          state.currentEvent = await fetchEvent(event.token);
        } catch {
          // Reminder changes are already saved; keep the current page stable if refresh fails.
        }
      },
    });
  }
  if (action === "delete-reminder") {
    const reminderId = element.dataset.reminderId;
    if (reminderId) {
      element.disabled = true;
      element.textContent = "…";
      try {
        await deleteReminder(reminderId);
        haptic("success");
        state.currentEvent = await fetchEvent(event.token);
        app.innerHTML = renderEvent(state.currentEvent);
      } catch {
        element.disabled = false;
        element.textContent = "✕";
      }
    }
  }
  if (action === "share") {
    hapticImpactFallback();
    const payload = await shareEvent(event.token);
    haptic("success");
    openTelegramLink(payload.url || event.share_url);
  }
  if (action === "register" && event.registration_url) {
    openLink(event.registration_url);
    registerEvent(event.token)
      .then((payload) => {
        if (Number.isFinite(payload?.attendee_count)) {
          setEventAttendeeCount(event.token, payload.attendee_count);
        }
      })
      .catch(() => null);
  }
}

function setEventAttendeeCount(token, count) {
  const normalized = Math.max(0, Number(count) || 0);
  const apply = (item) => {
    if (item?.token === token) {
      item.attendee_count = normalized;
    }
  };

  apply(state.currentEvent);
  state.events.forEach(apply);
  state.favorites.forEach(apply);
  state.reminders.forEach((group) => {
    group.reminders?.forEach((reminder) => apply(reminder.event));
  });
  state.currentEvent?.related_events?.forEach(apply);

  const value = app.querySelector("[data-attendee-count]");
  if (value && state.currentEvent?.token === token) {
    value.textContent = String(normalized);
  }
}

async function copyText(value) {
  if (!value) {
    return;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

async function toggleFavorite(event) {
  if (favoriteRequests.has(event.token)) {
    return;
  }
  favoriteRequests.add(event.token);
  const previous = event.is_favorite;
  event.is_favorite = !previous;
  setFavoriteButtonState(event.is_favorite, true);
  syncFavoriteState(event.token, event.is_favorite);
  setEventRowFavoriteBadge(event.token, event.is_favorite);
  haptic();
  try {
    if (event.is_favorite) {
      await addFavorite(event.token);
    } else {
      await removeFavorite(event.token);
      if (state.eventFilters.favoritesOnly) {
        state.events = state.events.filter((item) => item.token !== event.token);
      }
    }
    // We intentionally DO NOT nullify cachedMenuHTML here.
    // This allows the back navigation to instantly restore the menu from cache.
    // The navigation code will dynamically patch the badges and remove unfavorited items.
    haptic("success");
  } catch (error) {
    event.is_favorite = previous;
    syncFavoriteState(event.token, previous);
    setFavoriteButtonState(previous, false);
    setEventRowFavoriteBadge(event.token, previous);
    haptic("error");
  } finally {
    favoriteRequests.delete(event.token);
    setFavoriteButtonLoading(false);
    if (pendingEventsRefreshAfterFavorite && favoriteRequests.size === 0) {
      pendingEventsRefreshAfterFavorite = false;
      refreshEventsList({ animate: true });
    }
  }
}

function syncFavoriteState(token, isFavorite) {
  const apply = (item) => {
    if (item?.token === token) {
      item.is_favorite = isFavorite;
    }
  };

  state.events.forEach(apply);
  state.favorites.forEach(apply);
  state.reminders.forEach((group) => {
    group.reminders?.forEach((reminder) => apply(reminder.event));
  });
  state.currentEvent?.related_events?.forEach(apply);
}

function setEventRowFavoriteBadge(token, isFavorite) {
  app.querySelectorAll("[data-event-token]").forEach((row) => {
    if (row.dataset.eventToken !== token) {
      return;
    }
    const badges = row.querySelector(".row-badges");
    if (!badges) {
      return;
    }
    const existing = badges.querySelector("[data-favorite-badge]");
    if (isFavorite && !existing) {
      const badge = document.createElement("em");
      badge.dataset.favoriteBadge = "";
      badge.textContent = "★";
      badges.querySelector("em")?.after(badge);
    }
    if (!isFavorite) {
      existing?.remove();
    }
  });
}

function setFavoriteButtonState(isFavorite, animate) {
  const button = app.querySelector("[data-action='favorite']");
  if (!button) {
    return;
  }
  button.classList.toggle("active", isFavorite);
  setFavoriteButtonLoading(true);
  if (animate) {
    button.classList.remove("favorite-spin", "favorite-unspin");
    void button.offsetWidth;
    button.classList.add(isFavorite ? "favorite-spin" : "favorite-unspin");
  }
}

function setFavoriteButtonLoading(loading) {
  const button = app.querySelector("[data-action='favorite']");
  if (!button) {
    return;
  }
  button.disabled = loading;
  button.classList.toggle("is-loading", loading);
}

function isTopLevelRoute(route) {
  return route === "events" || route === "calendar";
}

function runCircularTransition(event, apply) {
  if (!document.startViewTransition || !event) {
    document.documentElement.classList.add("theme-transitioning");
    apply();
    window.setTimeout(() => {
      document.documentElement.classList.remove("theme-transitioning");
    }, 600);
    return;
  }

  const x = event.clientX || window.innerWidth / 2;
  const y = event.clientY || window.innerHeight / 2;
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  );

  document.documentElement.classList.add("theme-transitioning");

  const transition = document.startViewTransition(() => {
    document.documentElement.classList.add("no-transitions");
    apply();
  });

  transition.ready.then(() => {
    document.documentElement.animate(
      {
        clipPath: [
          `circle(0px at ${x}px ${y}px)`,
          `circle(${endRadius}px at ${x}px ${y}px)`,
        ],
      },
      {
        duration: 450,
        easing: "cubic-bezier(0.4, 0, 0.2, 1)",
        pseudoElement: "::view-transition-new(root)",
      },
    );
  });

  transition.finished.finally(() => {
    // Remove theme-transitioning FIRST so the favorite button's inline
    // color pin (set in renderEventPreservingFavorite) is released at the
    // same time no-transitions is lifted — preventing any color flash.
    document.documentElement.classList.remove("theme-transitioning");
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.documentElement.classList.remove("no-transitions");
      });
    });
  });
}

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (state.eventSearch.active) {
      closeEventSearch();
    }
    closeSheet();
    closeFilterSheet();
  }
});


let resendInterval = null;
let forgotResendInterval = null;

function startResendCountdown() {
  window.clearInterval(resendInterval);
  resendInterval = window.setInterval(() => {
    if (state.resendCooldown > 0) {
      state.resendCooldown--;
      const timerEl = app.querySelector(".resend-timer strong");
      if (timerEl) {
        timerEl.textContent = `${state.resendCooldown}s`;
      }
      if (state.resendCooldown <= 0) {
        window.clearInterval(resendInterval);
        renderCurrent({ quiet: true });
        initRatingsHandlers();
      }
    } else {
      window.clearInterval(resendInterval);
    }
  }, 1000);
}

function updateAuthSectionDOM(options = {}) {
  const app = document.querySelector(".auth-sheet-backdrop") || document.getElementById("app");
  const container = app.querySelector("#auth-profile-container");
  if (!container) {
    renderCurrent({ quiet: true });
    return;
  }
  const newContent = renderAuthSection(state.cachedRatingsProfile);
  const sheet = app.querySelector(".auth-bottom-sheet");

  if (!options.skipTransition && sheet) {
    // 1. Measure and lock current height to prevent instant content pop snaps
    const oldHeight = sheet.offsetHeight;
    sheet.style.height = `${oldHeight}px`;
    sheet.style.transition = "height 0.28s cubic-bezier(0.22, 1, 0.36, 1)";

    // 2. Smoothly fade out old content first
    container.style.transition = "opacity 0.12s ease-out, transform 0.12s ease-out";
    container.style.opacity = "0";
    container.style.transform = "translateY(-4px)";

    setTimeout(() => {
      // 3. Swap the DOM content
      container.innerHTML = newContent;
      initRatingsHandlers();

      // 4. Measure new target natural height
      sheet.style.height = "auto";
      const newHeight = sheet.offsetHeight;
      
      // 5. Restore back to old height temporarily
      sheet.style.height = `${oldHeight}px`;
      
      // Force immediate reflow/repaint
      sheet.offsetHeight;

      // 6. Smoothly transition the sheet height to the new container boundaries
      sheet.style.height = `${newHeight}px`;

      // 7. Render organic slide-up and fade-in animation for the new elements
      container.style.transition = "opacity 0.22s cubic-bezier(0.22, 1, 0.36, 1), transform 0.22s cubic-bezier(0.22, 1, 0.36, 1)";
      container.style.opacity = "0";
      container.style.transform = "translateY(8px)";
      
      // Force repaint on container
      container.offsetHeight;
      
      container.style.opacity = "1";
      container.style.transform = "translateY(0)";

      // 8. Clean up inline styles once transitions complete
      setTimeout(() => {
        sheet.style.height = "auto";
        sheet.style.transition = "";
      }, 300);
    }, 120);
  } else {
    container.innerHTML = newContent;
    initRatingsHandlers();
  }
}

function initRatingsHandlers() {
  const isAuthSheetOpen = document.querySelector(".auth-sheet-backdrop") !== null;
  if (state.route !== "ratings" && state.route !== "events" && !isAuthSheetOpen) return;

  const app = document.querySelector(".auth-sheet-backdrop") || document.getElementById("app");

  const profileTrigger = document.querySelector("#ratings-profile-trigger");
  if (profileTrigger) {
    profileTrigger.onclick = () => {
      haptic("light");
      openAuthSheet();
    };
  }

  const tabReg = app.querySelector("#tab-register-btn");
  if (tabReg) {
    tabReg.onclick = () => {
      haptic("light");
      state.authMode = "register";
      updateAuthSectionDOM({ skipTransition: true });
    };
  }

  const tabLogin = app.querySelector("#tab-login-btn");
  if (tabLogin) {
    tabLogin.onclick = () => {
      haptic("light");
      state.authMode = "login";
      updateAuthSectionDOM({ skipTransition: true });
    };
  }

  const changeEmail = app.querySelector("#change-email-btn");
  if (changeEmail) {
    changeEmail.onclick = () => {
      haptic("light");
      state.authMode = "register";
      updateAuthSectionDOM({ skipTransition: true });
    };
  }

  const resendBtn = app.querySelector("#resend-code-btn");
  if (resendBtn) {
    resendBtn.onclick = async () => {
      haptic("light");
      resendBtn.disabled = true;
      resendBtn.textContent = "Sending…";
      const errEl = app.querySelector("#auth-error-msg");
      errEl?.classList.add("hide");
      try {
        await resendCode(state.authEmail);
        haptic("success");
        state.resendCooldown = 60;
        updateAuthSectionDOM();
      } catch (err) {
        haptic("error");
        resendBtn.disabled = false;
        resendBtn.textContent = "Resend Code";
        if (errEl) {
          errEl.textContent = translateError(err.message) || t("failedToResendCode");
          errEl.classList.remove("hide");
        }
      }
    };
  }

  const emailInput = app.querySelector("#auth-email-field");
  if (emailInput) {
    emailInput.oninput = (e) => {
      const originalVal = e.target.value;
      const selectionStart = e.target.selectionStart;
      let val = originalVal.slice(0, 100).replace(/\s/g, "").replace(/[<>&"'/`\\;]/g, "");
      if (originalVal !== val) {
        e.target.value = val;
        const diff = originalVal.length - val.length;
        const newPos = Math.max(0, selectionStart - diff);
        e.target.setSelectionRange(newPos, newPos);
      }
      state.authEmail = val;
    };
    emailInput.onblur = (e) => {
      const val = e.target.value.trim();
      e.target.value = val;
      state.authEmail = val;
    };
  }

  const passwordInput = app.querySelector("#auth-password-field");
  if (passwordInput) {
    passwordInput.oninput = (e) => {
      const originalVal = e.target.value;
      const selectionStart = e.target.selectionStart;
      let val = originalVal.slice(0, 64).replace(/[<>&"'/`\\;]/g, "");
      if (val.startsWith(" ") || val.endsWith(" ")) {
        val = val.trim();
      }
      if (originalVal !== val) {
        e.target.value = val;
        const diff = originalVal.length - val.length;
        const newPos = Math.max(0, selectionStart - diff);
        e.target.setSelectionRange(newPos, newPos);
      }
      state.authPassword = val;
    };
  }

  const confirmPasswordInput = app.querySelector("#auth-confirm-password-field");
  if (confirmPasswordInput) {
    confirmPasswordInput.oninput = (e) => {
      const originalVal = e.target.value;
      const selectionStart = e.target.selectionStart;
      let val = originalVal.slice(0, 64).replace(/[<>&"'/`\\;]/g, "");
      if (val.startsWith(" ") || val.endsWith(" ")) {
        val = val.trim();
      }
      if (originalVal !== val) {
        e.target.value = val;
        const diff = originalVal.length - val.length;
        const newPos = Math.max(0, selectionStart - diff);
        e.target.setSelectionRange(newPos, newPos);
      }
      state.authConfirmPassword = val;
    };
  }

  app.querySelectorAll(".toggle-pass").forEach(btn => {
    btn.onclick = () => {
      haptic("light");
      state.authPasswordVisible = !state.authPasswordVisible;
      
      const pwdInput = app.querySelector("#auth-password-field");
      if (pwdInput) {
        pwdInput.type = state.authPasswordVisible ? "text" : "password";
      }
      const confirmInput = app.querySelector("#auth-confirm-password-field");
      if (confirmInput) {
        confirmInput.type = state.authPasswordVisible ? "text" : "password";
      }
      
      btn.classList.toggle("is-visible", state.authPasswordVisible);
      btn.setAttribute("aria-label", state.authPasswordVisible ? "Hide password" : "Show password");
      btn.setAttribute("title", state.authPasswordVisible ? "Hide password" : "Show password");
    };
  });

  const codeInput = app.querySelector("#auth-code-field");
  if (codeInput) {
    codeInput.oninput = (e) => {
      let val = e.target.value.replace(/[^0-9]/g, "").slice(0, 6);
      e.target.value = val;
      state.authCode = val;
    };
  }

  const credsForm = app.querySelector("#auth-credentials-form");
  if (credsForm) {
    credsForm.onsubmit = async (e) => {
      e.preventDefault();
      const email = app.querySelector("#auth-email-field").value.trim();
      const password = app.querySelector("#auth-password-field").value.trim();
      const isReg = (state.authMode || "login") === "register";
      const submitBtn = credsForm.querySelector(".auth-submit-btn");
      const errEl = app.querySelector("#auth-error-msg");
      
      errEl?.classList.add("hide");
      
      if (isReg) {
        const confirmPassword = app.querySelector("#auth-confirm-password-field").value.trim();
        if (password !== confirmPassword) {
          haptic("error");
          if (errEl) {
            errEl.textContent = t("confirmPasswordLabel") ? (t("passwordLabel") === "Пароль" ? "Пароли не совпадают." : (t("passwordLabel") === "Құпия сөз" ? "Құпия сөздер сәйкес келмейді." : "Passwords do not match.")) : "Passwords do not match.";
            errEl.classList.remove("hide");
          }
          return;
        }
      }

      submitBtn.disabled = true;
      const originalText = submitBtn.textContent;
      submitBtn.textContent = t("pleaseWait");

      try {
        if (isReg) {
          await register(email, password);
          haptic("success");
          state.authEmail = email;
          state.authConfirmPassword = "";
          state.authMode = "verify";
          state.resendCooldown = 60;
          updateAuthSectionDOM();
        } else {
          await login(email, password);
          haptic("success");
          state.authEmail = "";
          state.authPassword = "";
          state.authConfirmPassword = "";
          state.authMode = "register";
          if (state.reopenReviewToken) {
            const tokenToReopen = state.reopenReviewToken;
            state.reopenReviewToken = null;
            closeAuthSheet();
            state.route = "";
            await navigate("event", { token: tokenToReopen, keepScroll: true });
            const hasOwnReview = state.currentEvent?.reviews?.find(r => r.is_own);
            if (!hasOwnReview) {
              const modal = document.getElementById("app").querySelector("#review-submission-modal");
              if (modal) modal.classList.add("is-open");
            } else {
              const reviewsBlock = document.getElementById("app").querySelector("#reviews-section-anchor");
              reviewsBlock?.scrollIntoView({ behavior: "smooth" });
            }
          } else {
            closeAuthSheet();
            // Force a fresh ratings render even if we're already on that route
            state.route = "";
            await navigate("ratings", { replaceHash: false, quiet: true, keepScroll: true });
          }
        }
      } catch (err) {
        haptic("error");
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
        if (errEl) {
          errEl.textContent = translateError(err.message) || t("anErrorOccurred");
          errEl.classList.remove("hide");
        }
      }
    };
  }

  const verifyForm = app.querySelector("#verify-form");
  if (verifyForm) {
    if (state.resendCooldown > 0) {
      startResendCountdown();
    }
    verifyForm.onsubmit = async (e) => {
      e.preventDefault();
      const code = app.querySelector("#auth-code-field").value.trim();
      const submitBtn = verifyForm.querySelector(".auth-submit-btn");
      const errEl = app.querySelector("#auth-error-msg");

      errEl?.classList.add("hide");
      submitBtn.disabled = true;
      submitBtn.textContent = t("verifying");

      try {
        await verifyCode(state.authEmail, code);
        haptic("success");
        state.authEmail = "";
        state.authPassword = "";
        state.authConfirmPassword = "";
        state.authMode = "register";
        state.resendCooldown = 0;
        window.clearInterval(resendInterval);
        if (state.reopenReviewToken) {
          const tokenToReopen = state.reopenReviewToken;
          state.reopenReviewToken = null;
          closeAuthSheet();
          state.route = "";
          await navigate("event", { token: tokenToReopen, keepScroll: true });
          const hasOwnReview = state.currentEvent?.reviews?.find(r => r.is_own);
          if (!hasOwnReview) {
            const modal = document.getElementById("app").querySelector("#review-submission-modal");
            if (modal) modal.classList.add("is-open");
          } else {
            const reviewsBlock = document.getElementById("app").querySelector("#reviews-section-anchor");
            reviewsBlock?.scrollIntoView({ behavior: "smooth" });
          }
        } else {
          closeAuthSheet();
          // Force a fresh ratings render even if we're already on that route
          state.route = "";
          await navigate("ratings", { replaceHash: false, quiet: true, keepScroll: true });
        }
      } catch (err) {
        haptic("error");
        submitBtn.disabled = false;
        submitBtn.textContent = "Verify Code";
        if (errEl) {
          errEl.textContent = translateError(err.message) || t("invalidCode");
          errEl.classList.remove("hide");
        }
      }
    };
  }

  const logoutBtns = document.querySelectorAll("#logout-btn");
  logoutBtns.forEach((logoutBtn) => {
    logoutBtn.onclick = async () => {
      haptic("light");
      logoutBtn.disabled = true;
      logoutBtn.textContent = t("loggingOut");
      await logout();
      state.authEmail = "";
      state.authPassword = "";
      state.authConfirmPassword = "";
      closeAuthSheet();
      // Reset cached events and route guard so the events screen re-fetches
      state.events = [];
      cachedMenuHTML = null;
      state.route = "";
      await navigate("events", { replaceHash: false, quiet: false });
    };
  });

  app.querySelectorAll("[data-delete-review-token]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const token = btn.dataset.deleteReviewToken;
      const doDelete = () => {
        haptic("light");
        btn.disabled = true;
        deleteReview(token)
          .then(async () => {
            haptic("success");
            if (state.cachedRatingsProfile && state.cachedRatingsProfile.history) {
              state.cachedRatingsProfile.history = state.cachedRatingsProfile.history.filter(
                (item) => item.event_token !== token
              );
              if (document.querySelector(".auth-sheet-backdrop")) {
                updateAuthSectionDOM({ skipTransition: true });
              }
            } else {
              state.cachedRatingsProfile = null;
            }
            if (state.user && state.user.is_verified) {
              fetchProfile().then((p) => { 
                state.cachedRatingsProfile = p; 
                if (document.querySelector(".auth-sheet-backdrop")) {
                  updateAuthSectionDOM({ skipTransition: true });
                }
              }).catch(() => null);
            }
            if (!document.querySelector(".auth-sheet-backdrop")) {
              await navigate("ratings", { replaceHash: false, quiet: true });
            }
          })
          .catch(() => {
            haptic("error");
            btn.disabled = false;
          });
      };
      
      if (tg && tg.showConfirm) {
        tg.showConfirm("Are you sure you want to delete this rating and comment?", (ok) => {
          if (ok) doDelete();
        });
      } else if (confirm("Are you sure you want to delete this rating and comment?")) {
        doDelete();
      }
    };
  });

  app.querySelectorAll("[data-edit-review-token]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      haptic("light");
      const token = btn.dataset.editReviewToken;
      await navigate("event", { token });
      const reviewsBlock = document.getElementById("reviews-section-anchor");
      reviewsBlock?.scrollIntoView({ behavior: "smooth" });
    };
  });

  // ── Forgot password button (login tab only) ──
  const forgotBtn = app.querySelector("#forgot-password-btn");
  if (forgotBtn) {
    forgotBtn.onclick = () => {
      haptic("light");
      state.forgotStep = "email";
      state.forgotEmail = state.authEmail || "";
      state.forgotCode = "";
      state.forgotResendCooldown = 0;
      window.clearInterval(forgotResendInterval);
      updateAuthSectionDOM();
    };
  }

  initForgotPasswordHandlers();
}


function startForgotResendCountdown() {
  window.clearInterval(forgotResendInterval);
  forgotResendInterval = window.setInterval(() => {
    if (state.forgotResendCooldown > 0) {
      state.forgotResendCooldown--;
      const root = document.querySelector(".auth-sheet-backdrop") || app;
      const timerEl = root.querySelector(".resend-timer");
      if (timerEl) {
        // Update just the timer text in-place to avoid re-render
        const key = t("resendAvailableIn").replace("{sec}", state.forgotResendCooldown);
        timerEl.textContent = key;
      }
      if (state.forgotResendCooldown <= 0) {
        window.clearInterval(forgotResendInterval);
        updateAuthSectionDOM();
        initForgotPasswordHandlers();
      }
    } else {
      window.clearInterval(forgotResendInterval);
    }
  }, 1000);
}

function initForgotPasswordHandlers() {
  const isAuthSheetOpen = document.querySelector(".auth-sheet-backdrop") !== null;
  if (state.route !== "ratings" && !isAuthSheetOpen) return;
  if (!state.forgotStep) return;

  const root = document.querySelector(".auth-sheet-backdrop") || app;

  // ── Back button (all steps) ──
  const backBtn = root.querySelector("#forgot-back-btn");
  if (backBtn) {
    backBtn.onclick = () => {
      haptic("light");
      window.clearInterval(forgotResendInterval);
      if (state.forgotStep === "code" || state.forgotStep === "email") {
        state.forgotStep = null;
        state.forgotCode = "";
        state.forgotResendCooldown = 0;
      } else if (state.forgotStep === "newpwd") {
        state.forgotStep = "code";
      }
      updateAuthSectionDOM();
    };
  }

  // ── Step 1: Email form ──
  const emailForm = root.querySelector("#forgot-email-form");
  if (emailForm) {
    const emailInput = root.querySelector("#forgot-email-field");
    if (emailInput) {
      emailInput.oninput = (e) => {
        let val = e.target.value.slice(0, 100).replace(/\s/g, "").replace(/[<>&"'/`\\;]/g, "");
        e.target.value = val;
        state.forgotEmail = val;
      };
      emailInput.onblur = (e) => {
        const val = e.target.value.trim();
        e.target.value = val;
        state.forgotEmail = val;
      };
    }

    emailForm.onsubmit = async (e) => {
      e.preventDefault();
      const email = (root.querySelector("#forgot-email-field")?.value || "").trim();
      const submitBtn = emailForm.querySelector(".auth-submit-btn");
      const errEl = root.querySelector("#forgot-error-msg");
      const successEl = root.querySelector("#forgot-success-msg");

      errEl?.classList.add("hide");
      successEl?.classList.add("hide");
      submitBtn.disabled = true;
      const origText = submitBtn.textContent;
      submitBtn.textContent = t("loading") + "…";

      try {
        await forgotPasswordRequest(email);
        haptic("success");
        state.forgotEmail = email;
        state.forgotStep = "code";
        state.forgotCode = "";
        state.forgotResendCooldown = 60;
        updateAuthSectionDOM();
        startForgotResendCountdown();
      } catch (err) {
        haptic("error");
        submitBtn.disabled = false;
        submitBtn.textContent = origText;
        if (errEl) {
          errEl.textContent = translateError(err.message) || t("invalidOrExpiredCode");
          errEl.classList.remove("hide");
        }
      }
    };
  }

  // ── Step 2: Code form ──
  const codeForm = root.querySelector("#forgot-code-form");
  if (codeForm) {
    const codeInput = root.querySelector("#forgot-code-field");
    if (codeInput) {
      codeInput.oninput = (e) => {
        let val = e.target.value.replace(/[^0-9]/g, "").slice(0, 6);
        e.target.value = val;
        state.forgotCode = val;
      };
    }

    codeForm.onsubmit = async (e) => {
      e.preventDefault();
      const code = (root.querySelector("#forgot-code-field")?.value || "").trim();
      const submitBtn = codeForm.querySelector(".auth-submit-btn");
      const errEl = root.querySelector("#forgot-error-msg");

      errEl?.classList.add("hide");
      submitBtn.disabled = true;
      const origText = submitBtn.textContent;
      submitBtn.textContent = t("loading") + "…";

      try {
        await forgotPasswordVerify(state.forgotEmail, code);
        haptic("success");
        state.forgotCode = code;
        state.forgotStep = "newpwd";
        window.clearInterval(forgotResendInterval);
        updateAuthSectionDOM();
      } catch (err) {
        haptic("error");
        submitBtn.disabled = false;
        submitBtn.textContent = origText;
        if (errEl) {
          errEl.textContent = t("invalidOrExpiredCode");
          errEl.classList.remove("hide");
        }
      }
    };

    // Start the countdown if still ticking
    if (state.forgotResendCooldown > 0) {
      startForgotResendCountdown();
    }

    // Resend button
    const resendBtn = root.querySelector("#forgot-resend-btn");
    if (resendBtn) {
      resendBtn.onclick = async () => {
        haptic("light");
        resendBtn.disabled = true;
        resendBtn.textContent = t("loading") + "…";
        const errEl = root.querySelector("#forgot-error-msg");
        errEl?.classList.add("hide");
        try {
          await forgotPasswordRequest(state.forgotEmail);
          haptic("success");
          state.forgotResendCooldown = 60;
          updateAuthSectionDOM();
          startForgotResendCountdown();
        } catch (err) {
          haptic("error");
          resendBtn.disabled = false;
          resendBtn.textContent = t("resendCode");
          if (errEl) {
            errEl.textContent = translateError(err.message) || t("tooManyAttempts");
            errEl.classList.remove("hide");
          }
        }
      };
    }
  }

  // ── Step 3: New password form ──
  const resetForm = root.querySelector("#forgot-reset-form");
  if (resetForm) {
    // Password visibility toggle (reuses existing .toggle-pass pattern)
    resetForm.querySelectorAll(".toggle-pass").forEach(btn => {
      btn.onclick = () => {
        haptic("light");
        const targetId = btn.dataset.toggleFor;
        const input = resetForm.querySelector(`#${targetId}`);
        if (!input) return;
        const isVisible = input.type === "text";
        input.type = isVisible ? "password" : "text";
        btn.classList.toggle("is-visible", !isVisible);
      };
    });

    resetForm.onsubmit = async (e) => {
      e.preventDefault();
      const newPwd = (root.querySelector("#forgot-newpwd-field")?.value || "");
      const confirmPwd = (root.querySelector("#forgot-confirmpwd-field")?.value || "");
      const submitBtn = resetForm.querySelector(".auth-submit-btn");
      const errEl = root.querySelector("#forgot-error-msg");

      errEl?.classList.add("hide");

      if (newPwd !== confirmPwd) {
        haptic("error");
        if (errEl) {
          errEl.textContent = t("passwordsDoNotMatch");
          errEl.classList.remove("hide");
        }
        return;
      }

      submitBtn.disabled = true;
      const origText = submitBtn.textContent;
      submitBtn.textContent = t("loading") + "…";

      try {
        await forgotPasswordReset(state.forgotEmail, state.forgotCode, newPwd);
        haptic("success");

        // Reset all forgot-password state
        state.forgotStep = null;
        state.forgotEmail = "";
        state.forgotCode = "";
        state.forgotResendCooldown = 0;
        window.clearInterval(forgotResendInterval);

        // Switch to login tab and show success message
        state.authMode = "login";
        updateAuthSectionDOM();

        // Show a non-intrusive success banner
        requestAnimationFrame(() => {
          const container = root.querySelector("#auth-profile-container");
          if (container) {
            const banner = document.createElement("div");
            banner.className = "auth-success auth-reset-success";
            banner.textContent = t("passwordResetSuccess");
            container.prepend(banner);
            window.setTimeout(() => banner.remove(), 4000);
          }
        });
      } catch (err) {
        haptic("error");
        submitBtn.disabled = false;
        submitBtn.textContent = origText;
        if (errEl) {
          errEl.textContent = t("invalidOrExpiredCode");
          errEl.classList.remove("hide");
        }
      }
    };
  }
}

function initEventReviewsHandlers() {
  const form = app.querySelector("#event-review-form");
  
  const penTrigger = app.querySelector("#reviews-pen-trigger");
  if (penTrigger) {
    penTrigger.onclick = () => {
      haptic("light");
      const isVerified = state.user && state.user.is_verified;
      if (isVerified) {
        const modal = app.querySelector("#review-submission-modal");
        if (modal) modal.classList.add("is-open");
      } else {
        state.reopenReviewToken = state.currentEvent?.token;
        openAuthSheet();
      }
    };
  }

  const modalClose = app.querySelector("#review-modal-close");
  if (modalClose) {
    modalClose.onclick = () => {
      haptic("light");
      const modal = app.querySelector("#review-submission-modal");
      if (modal) modal.classList.remove("is-open");
    };
  }

  const modalBackdrop = app.querySelector("#review-submission-modal");
  if (modalBackdrop) {
    modalBackdrop.onclick = (e) => {
      if (e.target === modalBackdrop) {
        haptic("light");
        modalBackdrop.classList.remove("is-open");
      }
    };
  }

  const promoBtn = app.querySelector("#review-verify-btn");
  if (promoBtn) {
    promoBtn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      haptic("light");
      state.reopenReviewToken = state.currentEvent?.token;
      openAuthSheet();
    };
  }

  if (!form) return;

  const eventToken = state.currentEvent?.token;
  
  const starsContainer = form.querySelector(".star-rating-selector");
  const starBtns = form.querySelectorAll(".star-rating-selector .star-btn");
  const scoreField = form.querySelector("#review-score-field");

  starBtns.forEach((btn) => {
    btn.onclick = () => {
      const score = parseInt(btn.dataset.starScore || "0", 10);
      scoreField.value = score;
      starsContainer.dataset.selectedScore = score;
      
      starBtns.forEach((s) => {
        const sScore = parseInt(s.dataset.starScore || "0", 10);
        s.classList.toggle("active", sScore <= score);
      });
      
      const submitBtn = form.querySelector(".submit-review-btn");
      if (submitBtn) {
        submitBtn.disabled = score === 0;
      }
      
      haptic("light");
    };
  });

  const commentField = form.querySelector("#review-comment-field");
  if (commentField) {
    commentField.oninput = () => {
      let val = commentField.value;
      // Do not allow spaces first
      val = val.replace(/^\s+/, "");
      // Do not allow more than 1 consecutive space
      val = val.replace(/\s{2,}/g, " ");
      if (commentField.value !== val) {
        commentField.value = val;
      }
    };
  }

  form.onsubmit = async (e) => {
    e.preventDefault();
    const scoreVal = parseInt(scoreField.value, 10);
    const rawContent = commentField ? commentField.value : "";
    const submitBtn = form.querySelector(".submit-review-btn");
    const errEl = form.querySelector("#review-error-msg");

    if (isNaN(scoreVal) || scoreVal === 0) {
      haptic("error");
      if (errEl) {
        errEl.textContent = t("pleaseSelectStarRating");
        errEl.classList.remove("hide");
      }
      return;
    }

    if (rawContent && !rawContent.trim()) {
      haptic("error");
      if (errEl) {
        errEl.textContent = "Comments consisting only of spaces are invalid.";
        errEl.classList.remove("hide");
      }
      return;
    }

    // Clean hidden formatting / control characters (Cc, Cf, Cs, Co, Cn)
    let cleanedContent = rawContent.replace(/[\u200b-\u200d\uFEFF\u200e\u200f\u202a-\u202e\u0000-\u001f\u007f-\u009f]/g, "");
    // Compress consecutive spaces, tabs, and newlines to a single space
    cleanedContent = cleanedContent.replace(/\s+/g, " ").trim();

    if (cleanedContent.length > 256) {
      haptic("error");
      if (errEl) {
        errEl.textContent = "Comment cannot exceed 256 characters.";
        errEl.classList.remove("hide");
      }
      return;
    }

    errEl?.classList.add("hide");
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";

    try {
      await submitReview(eventToken, scoreVal, cleanedContent);
      haptic("success");
      const modal = app.querySelector("#review-submission-modal");
      if (modal) modal.classList.remove("is-open");
      state.cachedRatingsProfile = null;
      if (state.user && state.user.is_verified) {
        fetchProfile().then((p) => { state.cachedRatingsProfile = p; }).catch(() => null);
      }
      state.currentEvent = await fetchEvent(eventToken);
      app.innerHTML = renderEvent(state.currentEvent);
      initEventReviewsHandlers();
    } catch (err) {
      haptic("error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit";
      if (errEl) {
        errEl.textContent = translateError(err.message) || t("failedToSubmitReview");
        errEl.classList.remove("hide");
      }
    }
  };

  const deleteOwnBtn = form.querySelector("#delete-own-review-btn");
  if (deleteOwnBtn) {
    deleteOwnBtn.onclick = async () => {
      const doDelete = () => {
        haptic("light");
        deleteOwnBtn.disabled = true;
        deleteOwnBtn.textContent = "Deleting…";
        deleteReview(eventToken)
          .then(async () => {
            haptic("success");
            state.cachedRatingsProfile = null;
            if (state.user && state.user.is_verified) {
              fetchProfile().then((p) => { state.cachedRatingsProfile = p; }).catch(() => null);
            }
            state.currentEvent = await fetchEvent(eventToken);
            app.innerHTML = renderEvent(state.currentEvent);
            initEventReviewsHandlers();
          })
          .catch(() => {
            haptic("error");
            deleteOwnBtn.disabled = false;
            deleteOwnBtn.textContent = "Delete Review";
          });
      };

      if (tg && tg.showConfirm) {
        tg.showConfirm("Are you sure you want to delete your review?", (ok) => {
          if (ok) doDelete();
        });
      } else if (confirm("Are you sure you want to delete your review?")) {
        doDelete();
      }
    };
  }
}

let savedScrollY = 0;

export function openAuthSheet() {
  if (!document.querySelector(".auth-sheet-backdrop")) {
    savedScrollY = window.scrollY;
  }
  closeAuthSheet();
  document.documentElement.classList.add("sheet-open");
  const node = document.createElement("div");
  node.className = "sheet-backdrop auth-sheet-backdrop";
  node.innerHTML = `
    <section class="bottom-sheet auth-bottom-sheet" role="dialog" aria-modal="true">
      <div class="sheet-handle"></div>
      <div id="auth-profile-container" style="padding-top: 10px;">
        ${renderAuthSection(state.cachedRatingsProfile)}
      </div>
    </section>
  `;
  document.body.append(node);

  const sheet = node.querySelector(".auth-bottom-sheet");
  
  // High-fidelity swipe/drag down to close handlers
  let startY = 0;
  let currentY = 0;
  let isDragging = false;

  const onTouchStart = (e) => {
    if (e.target.closest("input, button, a, select, textarea")) return;
    startY = e.touches[0].clientY;
    currentY = startY;
    isDragging = true;
    sheet.classList.add("dragging");
    sheet.style.transition = "none";
  };

  const onTouchMove = (e) => {
    if (!isDragging) return;
    currentY = e.touches[0].clientY;
    const deltaY = currentY - startY;
    if (deltaY > 0) {
      sheet.style.transform = `translateY(${deltaY}px)`;
    } else {
      sheet.style.transform = "translateY(0)";
    }
  };

  const onTouchEnd = () => {
    if (!isDragging) return;
    isDragging = false;
    sheet.classList.remove("dragging");
    
    const deltaY = currentY - startY;
    sheet.style.transition = "transform 0.22s cubic-bezier(0.22, 1, 0.36, 1)";
    
    if (deltaY > 80) {
      sheet.style.transform = "translateY(104%)";
      closeAuthSheet();
    } else {
      sheet.style.transform = "translateY(0)";
    }
  };

  sheet.addEventListener("touchstart", onTouchStart, { passive: true });
  sheet.addEventListener("touchmove", onTouchMove, { passive: true });
  sheet.addEventListener("touchend", onTouchEnd, { passive: true });

  node.onclick = (e) => {
    if (e.target === node) closeAuthSheet();
  };

  // Silently re-establish the Telegram guest session if we don't have one.
  // This ensures the Bearer token is present when the user submits login/register,
  // preventing the "Missing session" error from the backend.
  if (!state.session) {
    authenticate().catch(() => null);
  }

  // If user is verified but the profile is not in the cache, fetch it asynchronously and re-render
  if (state.user && state.user.is_verified && !state.cachedRatingsProfile) {
    fetchProfile().then((profile) => {
      state.cachedRatingsProfile = profile;
      updateAuthSectionDOM({ skipTransition: true });
    }).catch(() => null);
  }

  initRatingsHandlers();
  requestAnimationFrame(() => {
    node.classList.add("open");
  });
}

export function closeAuthSheet() {
  const current = document.querySelector(".auth-sheet-backdrop");
  if (!current) return;
  current.classList.remove("open");
  if (!document.querySelector(".sheet-backdrop:not(.auth-sheet-backdrop)")) {
    document.documentElement.classList.remove("sheet-open");
  }
  requestAnimationFrame(() => {
    window.scrollTo(0, savedScrollY);
  });
  window.setTimeout(() => current.remove(), 220);
}


