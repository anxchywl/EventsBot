import {
  addFavorite,
  authenticate,
  createReminder,
  deleteReminder,
  fetchEvent,
  fetchEvents,
  fetchFavorites,
  fetchReminders,
  removeFavorite,
  shareEvent,
} from "./api.js";
import { loadingScreen, resetFallbackCoverStyles, startCountdowns } from "./components/events.js?v=20260525-card-spacing-align";
import { closeSheet, openReminderSheet } from "./components/sheets.js?v=20260525-card-spacing-align";
import { t } from "./i18n.js";
import { currentTheme, nextLang, rememberScroll, restoreScroll, setLang, setTheme, state, toggleTheme } from "./state.js";
import { configureBackButton, haptic, initTelegram, openLink, openTelegramLink, startParam, tg } from "./telegram.js";
import { renderEvent } from "./views/event.js";
import { renderFavorites } from "./views/favorites.js?v=20260525-card-spacing-align";
import { renderMenu, renderPlaceholder } from "./views/menu.js";
import { renderReminders } from "./views/reminders.js?v=20260525-card-spacing-align";

const app = document.getElementById("app");
let backHandler = () => navigate("events", { direction: "back" });

export async function boot() {
  setLang(state.lang);
  setTheme(state.theme || currentTheme());
  initTelegram(() => renderCurrent());
  await authenticate().catch(() => null);
  window.addEventListener("hashchange", () => loadFromLocation());
  app.addEventListener("click", onClick);
  loadFromLocation();
}

function routeFromLocation() {
  const start = startParam() || new URLSearchParams(window.location.search).get("startapp") || "";
  if (start.startsWith("event_")) {
    return { route: "event", token: start.slice(6) };
  }
  const pathEvent = window.location.pathname.match(/^\/events\/([^/]+)/);
  if (pathEvent) {
    return { route: "event", token: decodeURIComponent(pathEvent[1]) };
  }
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash.startsWith("events/")) {
    return { route: "event", token: hash.split("/")[1] };
  }
  if (["favorites", "reminders"].includes(hash)) {
    return { route: hash, token: "" };
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

  const performNavigation = async () => {
    state.route = route;
    state.token = options.token || "";
    configureBackButton(route !== "events", backHandler);
    await renderRoute({ quiet: options.quiet ?? isTopLevelRoute(route) });
    if (route === "events" || route === "favorites" || route === "reminders") {
      restoreScroll(route);
    } else {
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    if (options.replaceHash !== false) {
      syncHash(route, state.token);
    }
  };

  const isBack = options.direction === "back" || 
    (isTopLevelRoute(prevRoute) && isTopLevelRoute(targetRoute) && getRouteIndex(targetRoute) < getRouteIndex(prevRoute));

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
  }
}

function getRouteIndex(route) {
  const order = ["events", "favorites", "reminders"];
  return order.indexOf(route);
}

async function renderRoute({ quiet = false } = {}) {
  if (!quiet) {
    app.innerHTML = loadingScreen();
  }
  try {
    if (state.route === "event") {
      if (!state.token) {
        state.currentEvent = null;
        app.innerHTML = renderEvent(null);
        applyQuietRender(quiet);
        return;
      }
      state.currentEvent = await fetchEvent(state.token);
      app.innerHTML = renderEvent(state.currentEvent);
      applyQuietRender(quiet);
      return;
    }
    if (state.route === "favorites") {
      state.favorites = await fetchFavorites();
      app.innerHTML = renderFavorites(state.favorites);
      applyQuietRender(quiet);
      return;
    }
    if (state.route === "reminders") {
      state.reminders = await fetchReminders();
      app.innerHTML = renderReminders(state.reminders);
      applyQuietRender(quiet);
      return;
    }
    state.events = await fetchEvents();
    app.innerHTML = renderMenu(state.events);
    applyQuietRender(quiet);
  } catch (error) {
    if (state.route === "event" && error.status === 404) {
      app.innerHTML = renderEvent(null);
      applyQuietRender(quiet);
      return;
    }
    app.innerHTML = renderPlaceholder(state.route);
    applyQuietRender(quiet);
  }
}

function renderCurrent({ quiet = false } = {}) {
  if (state.route === "event") {
    app.innerHTML = renderEvent(state.currentEvent);
    applyQuietRender(quiet);
    return;
  }
  if (state.route === "favorites") {
    app.innerHTML = renderFavorites(state.favorites);
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
  const target = route === "events" ? "#/" : route === "event" ? `#/events/${token}` : `#/${route}`;
  if (window.location.hash !== target) {
    history.pushState(null, "", target);
  }
}

async function onClick(event) {
  const theme = event.target.closest("[data-action='theme']");
  if (theme) {
    runCircularTransition(event, () => {
      toggleTheme();
      resetFallbackCoverStyles();
      renderCurrent({ quiet: true });
    });
    haptic();
    return;
  }
  const lang = event.target.closest("[data-action='lang']");
  if (lang) {
    runCircularTransition(event, () => {
      nextLang();
      renderCurrent({ quiet: true });
    });
    haptic();
    return;
  }
  const reminderRemove = event.target.closest("[data-reminder-id]");
  if (reminderRemove) {
    await deleteReminder(reminderRemove.dataset.reminderId);
    haptic("success");
    await navigate("reminders", { replaceHash: false, quiet: true });
    return;
  }
  const favoriteRemove = event.target.closest("[data-favorite-remove]");
  if (favoriteRemove) {
    favoriteRemove.disabled = true;
    try {
      await removeFavorite(favoriteRemove.dataset.favoriteRemove);
      haptic("success");
      state.favorites = state.favorites.filter((item) => item.token !== favoriteRemove.dataset.favoriteRemove);
      app.innerHTML = renderFavorites(state.favorites);
      applyQuietRender(true);
    } catch {
      favoriteRemove.disabled = false;
      haptic("error");
    }
    return;
  }
  const row = event.target.closest("[data-event-token]");
  if (row) {
    await navigate("event", { token: row.dataset.eventToken });
    return;
  }
  const route = event.target.closest("button[data-route]");
  if (route) {
    await navigate(route.dataset.route, { quiet: true });
    return;
  }
  const action = event.target.closest("[data-action]");
  if (action) {
    await handleEventAction(action.dataset.action, action);
    return;
  }
}

async function handleEventAction(action, element) {
  const event = state.currentEvent;
  if (!event) return;
  if (action === "favorite") {
    await toggleFavorite(event);
  }
  if (action === "reminder") {
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
    const payload = await shareEvent(event.token);
    haptic("success");
    openTelegramLink(payload.url || event.share_url);
  }
  if (action === "register" && event.registration_url) {
    openLink(event.registration_url);
  }
}

async function toggleFavorite(event) {
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
    }
    haptic("success");
  } catch (error) {
    event.is_favorite = previous;
    syncFavoriteState(event.token, previous);
    setFavoriteButtonState(previous, false);
    setEventRowFavoriteBadge(event.token, previous);
    haptic("error");
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
  if (animate && isFavorite) {
    button.classList.remove("favorite-spin");
    void button.offsetWidth;
    button.classList.add("favorite-spin");
  }
}

function isTopLevelRoute(route) {
  return route === "events" || route === "favorites" || route === "reminders";
}

function runCircularTransition(event, apply) {
  if (!document.startViewTransition || !event) {
    apply();
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
    closeSheet();
  }
});
