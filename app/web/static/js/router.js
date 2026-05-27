import {
  addFavorite,
  authenticate,
  createReminder,
  deleteReminder,
  fetchEvent,
  fetchEventFilters,
  fetchEvents,
  fetchReminders,
  removeFavorite,
  shareEvent,
} from "./api.js";
import { loadingScreen, resetFallbackCoverStyles, startCountdowns } from "./components/events.js?v=20260527-no-event-filter-haptics";
import { closeFilterSheet, openFilterSheet } from "./components/filterSheet.js?v=20260528-gold-glow";
import { closeSheet, openReminderSheet } from "./components/sheets.js?v=20260528-gold-glow";
import { t } from "./i18n.js?v=20260528-gold-glow";
import { currentTheme, nextLang, normalizeEventFilters, rememberScroll, restoreScroll, setEventFilters, setLang, setTheme, state, toggleTheme } from "./state.js";
import { configureBackButton, haptic, initTelegram, openLink, openTelegramLink, startParam, tg } from "./telegram.js";
import { renderEvent, renderEventUnavailable, renderEventSkeleton } from "./views/event.js?v=20260528-gold-glow";
import { renderEventResults, renderFilterBar, renderMenu, renderPlaceholder } from "./views/menu.js?v=20260528-gold-glow";
import { renderReminders } from "./views/reminders.js?v=20260528-gold-glow";
import { renderCalendarInner, attachCalendarInteractions, refreshCalendarMonthPanels } from "./views/calendar.js?v=20260528-calendar-restore";

const app = document.getElementById("app");
let backHandler = () => navigate("events", { direction: "back" });
let eventFetchTimer = null;
let searchCloseTimer = null;
const favoriteRequests = new Set();
let pendingEventsRefreshAfterFavorite = false;
let lastDirectHapticAt = 0;

// Snapshot of the events menu DOM — saved when leaving for an event page,
// restored instantly when coming back so the transition is invisible.
let cachedMenuHTML = null;

let lastScrollY = window.scrollY;
let suppressNavScroll = false;

function handleScroll() {
  if (suppressNavScroll) return;
  const navElement = document.querySelector(".app-nav");
  if (!navElement) return;

  const currentScrollY = window.scrollY;
  const diff = currentScrollY - lastScrollY;

  if (currentScrollY <= 10) {
    navElement.classList.remove("nav-hidden");
  } else if (diff > 15) {
    navElement.classList.add("nav-hidden");
  } else if (diff < -15) {
    navElement.classList.remove("nav-hidden");
  }

  lastScrollY = currentScrollY;
}

export async function boot() {
  setLang(state.lang);
  setTheme(state.theme || currentTheme());
  initTelegram(() => renderCurrent());
  await authenticate().catch(() => null);
  window.addEventListener("hashchange", () => loadFromLocation());
  window.addEventListener("scroll", handleScroll, { passive: true });
  document.addEventListener("pointerdown", onPointerDown, { passive: true });
  document.addEventListener("touchstart", onPointerDown, { passive: true });
  document.addEventListener("click", onClick);
  app.addEventListener("input", onInput);
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
    return { route: "reminders", token: "" };
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
      } else if (route === "reminders") {
        prefetchedReminders = await fetchReminders();
      } else if (route === "events") {
        await ensureEventFilterOptions();
        if (returningFromEventWithLocalEvents) {
          prefetchedEvents = state.events;
          shouldRefreshEventsAfterNavigation = true;
        } else {
          prefetchedEvents = await fetchEvents(state.eventFilters);
        }
      } else if (route === "calendar") {
        if (state.events.length > 0) {
          prefetchedEvents = state.events;
        } else {
          prefetchedEvents = await fetchEvents(state.eventFilters);
        }
      }
    } catch (_) {
      // Pre-fetch failed — renderRoute will handle the error gracefully
    }
  }

  const performNavigation = async () => {
    state.route = route;
    state.token = options.token || "";
    if (route !== "events") {
      window.clearTimeout(searchCloseTimer);
      state.eventSearch.active = false;
      state.eventSearch.query = "";
      document.documentElement.classList.remove("event-searching", "event-search-closing");
    }
    configureBackButton(route !== "events", backHandler);

    if (restoringFromCache) {
      // Restore the events menu DOM from cache — synchronous, no network, no flicker.
      // Inject `no-enter` into the HTML string BEFORE parsing so CSS animations
      // (slideDown, slideUp, eventListRise, etc.) never fire on the restored nodes.
      suppressNavScroll = true;
      app.innerHTML = cachedMenuHTML.replace(/(<div class="screen)/, '$1 no-enter');

      // The cache was saved AFTER the click handler added `nav-hidden` to the nav
      // (to hide it while navigating to the event page). Strip that class so the
      // nav bar is always visible when returning to the events menu.
      const navEl = app.querySelector(".app-nav");
      if (navEl) {
        // Temporarily disable transitions so the nav becomes visible instantly
        // when restoring from cache on mobile devices — prevents a visible
        // slide/opacity lag when re-inserting the cached DOM.
        navEl.classList.add("no-transitions");
        navEl.classList.remove("nav-hidden");
        // Force reflow to apply the style changes immediately.
        void navEl.offsetWidth;
        // Re-enable transitions on the next frame so subsequent nav actions
        // still animate smoothly.
        requestAnimationFrame(() => navEl.classList.remove("no-transitions"));
      }

      restoreScroll(route);
      requestAnimationFrame(() => {
        lastScrollY = window.scrollY;
        navEl?.classList.remove("nav-hidden");
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

    // Inject pre-fetched data into state so renderRoute skips the network call
    if (prefetchedEvent !== null) {
      state.currentEvent = prefetchedEvent;
    } else if (prefetchedReminders !== null) {
      state.reminders = prefetchedReminders;
    } else if (prefetchedEvents !== null) {
      state.events = prefetchedEvents;
    }
    await renderRoute({ quiet: options.quiet ?? isTopLevelRoute(route), prefetched: true });
    if (route === "events" || route === "reminders" || route === "calendar") {
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
    await performNavigation();
  });

  try {
    await transition.finished;
  } finally {
    document.documentElement.classList.remove("page-transitioning");
    document.documentElement.removeAttribute("data-nav-direction");
    document.documentElement.classList.remove("full-page-transition");
  }
}

function getRouteIndex(route) {
  const order = ["events", "calendar", "reminders"];
  return order.indexOf(route);
}

async function renderRoute({ quiet = false, prefetched = false } = {}) {
  // If data was pre-fetched before the view transition, skip loading screen & network calls
  // so the DOM swap is synchronous and the animation is perfectly smooth.
  const useCache = prefetched &&
    ((state.route === "event" && state.currentEvent !== undefined) ||
      (state.route === "reminders" && state.reminders !== undefined) ||
      ((state.route === "events" || state.route === "calendar") && state.events !== undefined));

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
      return;
    }
    if (state.route === "reminders") {
      if (!useCache) {
        state.reminders = await fetchReminders();
      }
      app.innerHTML = renderReminders(state.reminders);
      applyQuietRender(quiet);
      return;
    }
    if (!useCache) {
      await ensureEventFilterOptions();
      state.events = await fetchEvents(state.eventFilters);
    }
    app.innerHTML = renderMenu(state.events);
    applyQuietRender(quiet);
    if (state.calendarMode) attachCalendarInteractions();
  } catch (error) {
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
  if (state.route === "reminders") {
    app.innerHTML = renderReminders(state.reminders);
    applyQuietRender(quiet);
    return;
  }
  app.innerHTML = renderMenu(state.events);
  applyQuietRender(quiet);
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
  const currentButton = app.querySelector(".event-screen [data-action='favorite']");
  app.innerHTML = renderEvent(state.currentEvent);

  const nextButton = app.querySelector(".event-screen [data-action='favorite']");
  if (!currentButton || !nextButton) {
    return;
  }

  currentButton.classList.toggle("active", Boolean(state.currentEvent?.is_favorite));
  currentButton.classList.remove("favorite-spin", "favorite-unspin", "is-loading");
  currentButton.disabled = false;
  nextButton.replaceWith(currentButton);
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
    state.events = await fetchEvents(state.eventFilters);
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
      toggleTheme();
      resetFallbackCoverStyles();
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
    rememberScroll(state.calendarMode ? "calendar" : "events");
    runCircularTransition(event, () => {
      state.calendarMode = !state.calendarMode;
      const screen = document.querySelector('[data-route="events"]');
      if (screen) {
        screen.classList.toggle("calendar-mode-active", state.calendarMode);
        calendarToggle.classList.toggle("mode-active", state.calendarMode);
        
        const titleH1 = screen.querySelector('.events-title-block h1');
        if (titleH1) {
          titleH1.textContent = state.calendarMode ? t("eventsCalendar") : t("events");
        }
        
        const eventsContainer = screen.querySelector('.events-mode-container');
        const calendarContainer = screen.querySelector('.calendar-mode-container');
        
        if (state.calendarMode && calendarContainer && !calendarContainer.innerHTML.trim()) {
             import("./views/calendar.js?v=20260528-calendar-restore").then(({ renderCalendarInner }) => {
             calendarContainer.innerHTML = renderCalendarInner(state.events);
             attachCalendarInteractions();
           });
        }
        
        if (eventsContainer) eventsContainer.classList.toggle("mode-hidden", state.calendarMode);
        if (calendarContainer) calendarContainer.classList.toggle("mode-hidden", !state.calendarMode);
      }
      
      if (state.calendarMode && document.querySelector('.calendar-widget-container')) {
        attachCalendarInteractions();
      }
      restoreScroll(state.calendarMode ? "calendar" : "events");
    });
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
    document.querySelector(".app-nav")?.classList.add("nav-hidden");
    await navigate("event", { token: row.dataset.eventToken, quiet: true });
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
  state.eventSearch.query = searchInput.value;
  patchEventsList({ quiet: true });
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
  return route === "events" || route === "calendar" || route === "reminders";
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
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.documentElement.classList.remove("no-transitions");
        document.documentElement.classList.remove("theme-transitioning");
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
