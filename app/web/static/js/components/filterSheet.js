import { escapeAttr, escapeHtml } from "./events.js";
import { categoryLabel, t } from "../i18n.js?v=20260529-flicker-fix-v10";
import { state } from "../state.js";

const SORT_GROUPS = [
  ["time", [["time_asc", "nearestFirst"], ["time_desc", "furthestFirst"]]],
  ["reminders", [["reminders_desc", "mostReminders"], ["reminders_asc", "leastReminders"]]],
  ["participants", [["participants_desc", "mostParticipants"], ["participants_asc", "leastParticipants"]]],
];

const RELEVANCE_OPTIONS = [
  ["active", "active"],
  ["all", "all"],
  ["archived", "archived"],
];

const TIME_OF_DAY_OPTIONS = [
  { value: "morning", label: "morning" },
  { value: "afternoon", label: "afternoon" },
  { value: "evening", label: "evening" },
  { value: "night", label: "night" },
];

export function openFilterSheet({ type, onChange }) {
  closeFilterSheet();
  document.documentElement.classList.add("sheet-open");
  const node = document.createElement("div");
  node.className = "sheet-backdrop filter-sheet-backdrop";
  node.innerHTML = buildSheet(type);
  document.body.append(node);
  wireSheet(node, type, onChange);
  requestAnimationFrame(() => node.classList.add("open"));
}

export function closeFilterSheet() {
  const current = document.querySelector(".filter-sheet-backdrop");
  if (!current) return;
  current.classList.remove("open");
  if (!document.querySelector(".sheet-backdrop:not(.filter-sheet-backdrop)")) {
    document.documentElement.classList.remove("sheet-open");
  }
  window.setTimeout(() => current.remove(), 220);
}

function buildSheet(type) {
  return `
    <section class="bottom-sheet filter-sheet" role="dialog" aria-modal="true" data-filter-sheet="${escapeAttr(type)}">
      <div class="sheet-handle" data-sheet-drag></div>
      <div class="sheet-header">
        <h2>${escapeHtml(sheetTitle(type))}</h2>
      </div>
      ${sheetBody(type)}
    </section>
  `;
}

function sheetTitle(type) {
  if (type === "sorting") return t("sorting");
  if (type === "relevance") return t("relevance");
  if (type === "categories") return t("categories");
  if (type === "locations") return t("location");
  if (type === "timeOfDay") return t("timeOfDay");
  return t("organizers");
}

function sheetBody(type) {
  if (type === "sorting") {
    return SORT_GROUPS.map(([label, options]) => `
      <div class="filter-option-group">
        <p>${escapeHtml(t(label))}</p>
        ${options.map(([value, text]) => optionButton("sort", value, t(text), state.eventFilters.sort === value)).join("")}
      </div>
    `).join("");
  }
  if (type === "relevance") {
    return `
      <div class="filter-option-group">
        ${RELEVANCE_OPTIONS.map(([value, text]) => optionButton("relevance", value, t(text), state.eventFilters.relevance === value)).join("")}
      </div>
    `;
  }
  return multiSelectBody(type);
}

function optionButton(kind, value, label, active) {
  return `
    <button class="filter-option ${active ? "active" : ""}" type="button" data-filter-set="${kind}" data-value="${escapeAttr(value)}">
      <span>${escapeHtml(label)}</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 16.6 4.9 12.3l1.4-1.4 2.9 2.9 8.5-8.5 1.4 1.4z" fill="currentColor"/></svg>
    </button>
  `;
}

function multiSelectBody(type) {
  const values = state.eventFilters[type] || [];
  const options = type === "timeOfDay" ? TIME_OF_DAY_OPTIONS : (state.eventFilterOptions[type] || []);
  const labelFor = type === "categories" ? categoryLabel : (type === "timeOfDay" ? (value) => t(value) : (value) => value);
  return `
    ${type === "timeOfDay" ? "" : `
    <div class="filter-search-wrap">
      <input class="filter-search" type="search" placeholder="${escapeAttr(t("search"))}" data-filter-search maxlength="100" autocomplete="off" />
    </div>
    `}
    <div class="filter-chip-grid" data-filter-options>
      ${options.map((option) => {
        const active = values.includes(option.value);
        return `
          <button class="selector-chip ${active ? "active" : ""}" type="button" data-filter-toggle="${escapeAttr(type)}" data-value="${escapeAttr(option.value)}">
            ${escapeHtml(labelFor(option.label || option.value))}
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function wireSheet(node, type, onChange) {
  node.addEventListener("click", (event) => {
    if (event.target === node) {
      closeFilterSheet();
      return;
    }
    const single = event.target.closest("[data-filter-set]");
    if (single) {
      onChange({ [single.dataset.filterSet]: single.dataset.value });
      closeFilterSheet();
      return;
    }
    const toggle = event.target.closest("[data-filter-toggle]");
    if (toggle) {
      const key = toggle.dataset.filterToggle;
      const value = toggle.dataset.value;
      const current = new Set(state.eventFilters[key] || []);
      if (current.has(value)) {
        current.delete(value);
      } else {
        current.add(value);
      }
      toggle.classList.toggle("active", current.has(value));
      onChange({ [key]: [...current].sort() });
    }
  });

  const searchInput = node.querySelector("[data-filter-search]");
  if (searchInput) {
    searchInput.addEventListener("input", (event) => {
      // Sanitize in real-time (max 100 length, no SQL/script chars)
      let val = event.target.value.slice(0, 100).replace(/[<>&"'/`\\;]/g, "");
      // Do not accept leading spaces, and collapse multiple consecutive spaces to a single space
      val = val.replace(/^\s+/, "").replace(/\s{2,}/g, " ");
      event.target.value = val;

      const query = val.trim().toLowerCase();
      node.querySelectorAll("[data-filter-toggle]").forEach((button) => {
        button.hidden = query && !button.textContent.toLowerCase().includes(query);
      });
    });

    searchInput.addEventListener("blur", (event) => {
      // Strip any trailing spaces on focus out / blur
      let val = event.target.value.trim();
      event.target.value = val;
      const query = val.toLowerCase();
      node.querySelectorAll("[data-filter-toggle]").forEach((button) => {
        button.hidden = query && !button.textContent.toLowerCase().includes(query);
      });
    });
  }

  wireDragClose(node);
}

function wireDragClose(node) {
  const sheet = node.querySelector(".bottom-sheet");
  if (!sheet) return;
  let startY = 0;
  let currentY = 0;
  let dragging = false;

  sheet.addEventListener("pointerdown", (event) => {
    if (!event.target.closest("[data-sheet-drag], .sheet-header")) return;
    dragging = true;
    startY = event.clientY;
    currentY = 0;
    sheet.setPointerCapture?.(event.pointerId);
    sheet.classList.add("dragging");
  });

  sheet.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    currentY = Math.max(0, event.clientY - startY);
    sheet.style.transform = `translateY(${currentY}px)`;
  });

  sheet.addEventListener("pointerup", () => {
    if (!dragging) return;
    dragging = false;
    sheet.classList.remove("dragging");
    sheet.style.transform = "";
    if (currentY > 76) {
      closeFilterSheet();
    }
  });
}
