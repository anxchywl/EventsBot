import { escapeAttr, escapeHtml } from "./events.js?v=20260721-timeline-v7";
import { formatReminderOffset, t, translateError } from "../i18n.js?v=20260721-timeline-v7";

const MAX_REMINDERS = 3;

// expose reminder sheet controls

export function openReminderSheet({ event, onSubmit }) {
  closeSheet();
  document.documentElement.classList.add("sheet-open");
  const node = document.createElement("div");
  node.className = "sheet-backdrop reminder-sheet-backdrop";
  node.innerHTML = buildSheet(event);
  node._deletedReminderIds = new Set();
  document.body.append(node);
  refreshReminderInputs(node);

  // keep segmented timer inputs synchronized
  const segs = node.querySelectorAll(".timer-seg");
  segs.forEach((seg, i) => wireSegment(seg, i, segs));

  requestAnimationFrame(() => {
    node.classList.add("open");
    // wait for sheet animation before focusing inputs
    setTimeout(() => segs[0]?.focus(), 220);
  });

  node.addEventListener("click", async (e) => {
    if (e.target === node || e.target.closest("[data-sheet-close]")) {
      closeSheet();
      return;
    }

    const removeBtn = e.target.closest("[data-reminder-remove]");
    if (removeBtn) {
      const id = removeBtn.dataset.reminderRemove;
      if (id) node._deletedReminderIds.add(id);
      removeBtn.closest(".reminder-chip")?.remove();
      refreshReminderStack(node);
      refreshReminderInputs(node);
      return;
    }

    if (e.target.closest("[data-sheet-save]")) {
      await handleSave(node, event, onSubmit);
      return;
    }

    const preset = e.target.closest("[data-preset-minutes]");
    if (preset) {
      writeOffset(node, Number(preset.dataset.presetMinutes || 0));
      clearError(node);
    }
  });
}

// close reminder sheet and clear transient state
export function closeSheet() {
  const current = document.querySelector(".reminder-sheet-backdrop");
  if (!current) return;
  current.classList.remove("open");
  if (!document.querySelector(".sheet-backdrop:not(.reminder-sheet-backdrop)")) {
    document.documentElement.classList.remove("sheet-open");
  }
  window.setTimeout(() => current.remove(), 220);
}

// build reminder sheet markup

function buildSheet(event) {
  const atLimit = (event?.reminder_offsets?.length ?? 0) >= MAX_REMINDERS;
  return `
    <section class="bottom-sheet filter-sheet reminder-sheet" role="dialog" aria-modal="true">
      <div class="sheet-handle" data-sheet-drag></div>
      <div class="sheet-header">
        <h2>${t("reminderTitle")}</h2>
      </div>

      <div class="preset-grid" aria-label="${t("reminderTitle")}">
        ${presetButton(60, t("reminderPreset1h"), atLimit)}
        ${presetButton(180, t("reminderPreset3h"), atLimit)}
        ${presetButton(1440, t("reminderPreset1d"), atLimit)}
        ${presetButton(4320, t("reminderPreset3d"), atLimit)}
      </div>

      <div class="timer-wrap ${atLimit ? "timer-disabled" : ""}">
        <div class="timer-display">
          <div class="timer-field">
            <input
              class="timer-seg"
              type="text"
              inputmode="numeric"
              maxlength="2"
              placeholder="00"
              data-seg="dd"
              data-max="99"
              aria-label="${escapeAttr(t("timerLabelDays"))}"
              ${atLimit ? "disabled" : ""}
            />
            <span class="timer-label">${escapeHtml(t("timerLabelDays"))}</span>
          </div>
          <span class="timer-colon">:</span>
          <div class="timer-field">
            <input
              class="timer-seg"
              type="text"
              inputmode="numeric"
              maxlength="2"
              placeholder="00"
              data-seg="hh"
              data-max="23"
              aria-label="${escapeAttr(t("timerLabelHours"))}"
              ${atLimit ? "disabled" : ""}
            />
            <span class="timer-label">${escapeHtml(t("timerLabelHours"))}</span>
          </div>
          <span class="timer-colon">:</span>
          <div class="timer-field">
            <input
              class="timer-seg"
              type="text"
              inputmode="numeric"
              maxlength="2"
              placeholder="00"
              data-seg="mm"
              data-max="59"
              aria-label="${escapeAttr(t("timerLabelMinutes"))}"
              ${atLimit ? "disabled" : ""}
            />
            <span class="timer-label">${escapeHtml(t("timerLabelMinutes"))}</span>
          </div>
        </div>
        <p class="timer-error" data-error></p>
      </div>

      ${buildReminderStack(event)}

      <div class="sheet-actions">
        <button class="action primary sheet-save-btn" type="button" data-sheet-save>
          ${t("save")}
        </button>
        <button class="action" type="button" data-sheet-close>${t("cancel")}</button>
      </div>
    </section>
  `;
}

// render one preset reminder option
function presetButton(minutes, label, disabled) {
  return `
    <button class="preset-chip" type="button" data-preset-minutes="${minutes}" ${disabled ? "disabled" : ""}>
      ${escapeHtml(label)}
    </button>
  `;
}

// render existing reminders for the event
function buildReminderStack(event) {
  const ids = event?.reminder_ids ?? [];
  const offsets = event?.reminder_offsets ?? [];

  if (!offsets.length) return "";

  const chips = offsets.map((offset, i) => `
    <div class="reminder-chip">
      <span class="reminder-chip-time">${escapeHtml(formatReminderOffset(offset))}</span>
      <button class="reminder-chip-remove" type="button" data-reminder-remove="${escapeHtml(String(ids[i] ?? ""))}" aria-label="${t("remove")}">×</button>
    </div>
  `).join("");

  return `
    <div class="reminder-stack" data-reminder-stack>
      <div class="reminder-chips" data-chips>${chips}</div>
    </div>
  `;
}

// update reminder list after changes
function refreshReminderStack(node) {
  const stack = node.querySelector("[data-reminder-stack]");
  if (stack && !stack.querySelector(".reminder-chip")) stack.remove();
}

// reset custom reminder inputs after save
function refreshReminderInputs(node) {
  const atLimit = node.querySelectorAll(".reminder-chip").length >= MAX_REMINDERS;
  node.querySelector(".timer-wrap")?.classList.toggle("timer-disabled", atLimit);
  node.querySelectorAll(".timer-seg").forEach((input) => {
    input.disabled = atLimit;
    if (atLimit) input.value = "";
  });
  node.querySelectorAll("[data-preset-minutes]").forEach((button) => {
    button.disabled = atLimit;
  });
  if (!atLimit) clearError(node);
}

// keep custom day hour minute inputs valid

function wireSegment(seg, index, allSegs) {
  seg.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && seg.value === "" && index > 0) {
      allSegs[index - 1].focus();
      allSegs[index - 1].select();
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowLeft" && index > 0) {
      allSegs[index - 1].focus();
      allSegs[index - 1].select();
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowRight" && index < allSegs.length - 1) {
      allSegs[index + 1].focus();
      allSegs[index + 1].select();
      e.preventDefault();
      return;
    }
    if (!/^[0-9]$/.test(e.key) && !["Backspace", "Delete", "Tab", "ArrowLeft", "ArrowRight"].includes(e.key)) {
      e.preventDefault();
    }
  });

  seg.addEventListener("input", () => {
    seg.value = seg.value.replace(/\D/g, "");

    const max = Number(seg.dataset.max);
    const val = Number(seg.value);

    // clamp impossible two-digit values early
    if (seg.value.length === 1) {
      const maxFirstDigit = Math.floor(max / 10);
      if (val > maxFirstDigit) {
        seg.value = String(Math.min(val, max)).padStart(2, "0");
        advanceFocus(index, allSegs);
        return;
      }
    }

    if (seg.value.length >= 2) {
      seg.value = String(Math.min(val, max)).padStart(2, "0");
      advanceFocus(index, allSegs);
    }
  });

  seg.addEventListener("focus", () => seg.select());

  seg.addEventListener("paste", (e) => {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData("text");
    const digits = text.replace(/\D/g, "").slice(0, 2);
    seg.value = digits;
    seg.dispatchEvent(new Event("input"));
  });
}

// move focus to the next timer segment
function advanceFocus(index, allSegs) {
  if (index < allSegs.length - 1) {
    allSegs[index + 1].focus();
    allSegs[index + 1].select();
  }
}

// persist reminder changes from the sheet

function readOffset(node) {
  const dd = Number(node.querySelector("[data-seg='dd']")?.value || 0);
  const hh = Number(node.querySelector("[data-seg='hh']")?.value || 0);
  const mm = Number(node.querySelector("[data-seg='mm']")?.value || 0);
  return dd * 1440 + hh * 60 + mm;
}

// convert total minutes back into segmented inputs
function writeOffset(node, minutes) {
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  const values = { dd: days, hh: hours, mm: mins };
  Object.entries(values).forEach(([key, value]) => {
    const input = node.querySelector(`[data-seg='${key}']`);
    if (input) {
      input.value = String(value).padStart(2, "0");
    }
  });
  node.querySelector("[data-seg='mm']")?.focus();
}

// animate sheet validation errors
function showError(node, msg) {
  const el = node.querySelector("[data-error]");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("timer-error-shake");
  void el.offsetWidth; // restart error animation
  el.classList.add("timer-error-shake");
}

// clear sheet validation errors
function clearError(node) {
  const el = node.querySelector("[data-error]");
  if (el) {
    el.textContent = "";
    el.classList.remove("timer-error-shake");
  }
}

// validate and save custom reminder offsets
async function handleSave(node, event, onSubmit) {
  clearError(node);
  const offset = readOffset(node);
  const deletedReminderIds = [...(node._deletedReminderIds || [])];

  if (offset > 143_999) {
    showError(node, t("invalidReminder"));
    return;
  }

  const saveBtn = node.querySelector("[data-sheet-save]");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "…";
  }

  try {
    await onSubmit(offset > 0 ? offset : null, deletedReminderIds);
    closeSheet();
  } catch (err) {
    const msg = translateError(err?.message) || t("invalidReminder");
    showError(node, msg);
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = t("save");
    }
  }
}
