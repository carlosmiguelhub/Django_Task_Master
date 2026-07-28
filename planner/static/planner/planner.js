(function () {
  "use strict";

  const app = document.getElementById("plannerApp");
  if (!app) return;

  const calendar = document.getElementById("plannerCalendar");
  const loading = document.getElementById("plannerLoading");
  const periodLabel = document.getElementById("plannerPeriodLabel");
  const toast = document.getElementById("plannerToast");
  const boardFilter = document.getElementById("plannerBoardFilter");
  const statusFilter = document.getElementById("plannerStatusFilter");
  const sourceFilters = Array.from(document.querySelectorAll("[data-source-filter]"));
  const viewButtons = Array.from(document.querySelectorAll("[data-view]"));

  const dialog = document.getElementById("plannerEventDialog");
  const eventForm = document.getElementById("plannerEventForm");
  const eventId = document.getElementById("plannerEventId");
  const eventTitle = document.getElementById("plannerEventTitle");
  const eventDescription = document.getElementById("plannerEventDescription");
  const eventAllDay = document.getElementById("plannerEventAllDay");
  const startDateInput = document.getElementById("plannerStartDate");
  const startTimeInput = document.getElementById("plannerStartTime");
  const endDateInput = document.getElementById("plannerEndDate");
  const endTimeInput = document.getElementById("plannerEndTime");
  const formError = document.getElementById("plannerFormError");
  const deleteButton = document.getElementById("deletePlannerEvent");
  const dialogTitle = document.getElementById("plannerDialogTitle");

  const state = {
    view: localStorage.getItem("taskmaster-planner-view") || "month",
    anchor: new Date(),
    items: [],
    rangeStart: null,
    rangeEnd: null,
    toastTimer: null,
  };

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  });
  const shortDateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  });
  const fullDateFormatter = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const weekdayFormatter = new Intl.DateTimeFormat(undefined, { weekday: "short" });
  const timeFormatter = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function dateKey(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function parseDateKey(value) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function addDays(date, days) {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result;
  }

  function startOfWeek(date) {
    const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const mondayOffset = (result.getDay() + 6) % 7;
    result.setDate(result.getDate() - mondayOffset);
    return result;
  }

  function monthRange(date) {
    const first = new Date(date.getFullYear(), date.getMonth(), 1);
    const start = startOfWeek(first);
    return { start, end: addDays(start, 41) };
  }

  function currentRange() {
    if (state.view === "month") return monthRange(state.anchor);
    if (state.view === "week") {
      const start = startOfWeek(state.anchor);
      return { start, end: addDays(start, 6) };
    }
    const start = new Date(
      state.anchor.getFullYear(),
      state.anchor.getMonth(),
      state.anchor.getDate()
    );
    return { start, end: addDays(start, 44) };
  }

  function itemDate(item) {
    if (item.all_day && /^\d{4}-\d{2}-\d{2}$/.test(item.start)) {
      return parseDateKey(item.start);
    }
    return new Date(item.start);
  }

  function itemDateKey(item) {
    return dateKey(itemDate(item));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function groupByDate(items) {
    return items.reduce((groups, item) => {
      const key = itemDateKey(item);
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
      return groups;
    }, {});
  }

  function getCookie(name) {
    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith(`${name}=`));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "The request could not be completed.");
    return payload;
  }

  function showToast(message, isError = false) {
    clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.classList.toggle("is-error", isError);
    toast.hidden = false;
    state.toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, 3200);
  }

  function enabledSources() {
    return new Set(
      sourceFilters.filter((input) => input.checked).map((input) => input.dataset.sourceFilter)
    );
  }

  function filteredItems() {
    const sources = enabledSources();
    const board = boardFilter.value;
    const status = statusFilter.value;

    return state.items
      .filter((item) => sources.has(item.source))
      .filter((item) => !board || String(item.board_id) === board)
      .filter((item) => {
        if (!status) return true;
        if (item.source !== "task") return false;
        if (status === "overdue") return item.overdue;
        return item.status === status && !item.overdue;
      })
      .sort((a, b) => itemDate(a) - itemDate(b));
  }

  function updateSummary(items) {
    document.getElementById("visibleTaskCount").textContent = items.filter(
      (item) => item.source === "task"
    ).length;
    document.getElementById("visibleEventCount").textContent = items.filter(
      (item) => item.source === "event"
    ).length;
    document.getElementById("visibleOverdueCount").textContent = items.filter(
      (item) => item.overdue
    ).length;
  }

  function itemClasses(item) {
    return [
      `source-${item.source}`,
      `status-${item.status}`,
      item.overdue ? "is-overdue" : "",
    ]
      .filter(Boolean)
      .join(" ");
  }

  function itemTime(item) {
    return item.all_day ? "All day" : timeFormatter.format(itemDate(item));
  }

  function itemMarkup(item, includeTime = false) {
    return `
      <button
        type="button"
        class="planner-item ${itemClasses(item)}"
        data-planner-item="${escapeHtml(item.id)}"
        draggable="true"
        title="${escapeHtml(`${item.title} · ${item.board}`)}"
      >
        ${includeTime ? `<span class="planner-item-time">${escapeHtml(itemTime(item))}</span>` : ""}
        <span>${escapeHtml(item.title)}</span>
      </button>
    `;
  }

  function attachItemInteractions(root) {
    root.querySelectorAll("[data-planner-item]").forEach((element) => {
      const item = state.items.find((entry) => entry.id === element.dataset.plannerItem);
      if (!item) return;

      element.addEventListener("click", (event) => {
        event.stopPropagation();
        openItem(item);
      });

      element.addEventListener("dragstart", (event) => {
        event.stopPropagation();
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData(
          "application/json",
          JSON.stringify({
            source: item.source,
            item_id: item.item_id,
          })
        );
      });
    });
  }

  function attachDropTarget(element, targetDate) {
    element.addEventListener("dragover", (event) => {
      event.preventDefault();
      element.classList.add("is-drag-over");
    });
    element.addEventListener("dragleave", () => {
      element.classList.remove("is-drag-over");
    });
    element.addEventListener("drop", async (event) => {
      event.preventDefault();
      element.classList.remove("is-drag-over");
      try {
        const payload = JSON.parse(event.dataTransfer.getData("application/json"));
        await apiRequest(app.dataset.rescheduleUrl, {
          method: "POST",
          body: JSON.stringify({ ...payload, date: dateKey(targetDate) }),
        });
        showToast("Schedule updated.");
        await loadItems();
      } catch (error) {
        showToast(error.message || "Unable to reschedule this item.", true);
      }
    });
  }

  function renderMonth(items) {
    const { start } = monthRange(state.anchor);
    const grouped = groupByDate(items);
    const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    let html = `<div class="planner-month">`;
    html += weekdays
      .map((weekday) => `<div class="planner-weekday">${weekday}</div>`)
      .join("");

    for (let index = 0; index < 42; index += 1) {
      const day = addDays(start, index);
      const key = dateKey(day);
      const dayItems = grouped[key] || [];
      const outside = day.getMonth() !== state.anchor.getMonth();
      const today = key === dateKey(new Date());
      const past = key < dateKey(new Date());
      html += `
        <div class="planner-day ${outside ? "is-outside" : ""} ${today ? "is-today" : ""} ${past ? "is-past" : ""}" data-date="${key}">
          <div class="planner-day-number">${day.getDate()}</div>
          <div class="planner-day-items">
            ${dayItems.slice(0, 3).map((item) => itemMarkup(item)).join("")}
            ${dayItems.length > 3 ? `<div class="planner-more">+${dayItems.length - 3} more</div>` : ""}
          </div>
        </div>
      `;
    }
    html += `</div>`;
    calendar.innerHTML = html;

    calendar.querySelectorAll(".planner-day").forEach((dayElement) => {
      const day = parseDateKey(dayElement.dataset.date);
      dayElement.addEventListener("click", () => {
        if (dayElement.dataset.date < dateKey(new Date())) {
          showToast("New events can only be added today or later.", true);
          return;
        }
        openCreateDialog(dayElement.dataset.date);
      });
      attachDropTarget(dayElement, day);
    });
    attachItemInteractions(calendar);
  }

  function renderWeek(items) {
    const weekStart = startOfWeek(state.anchor);
    const grouped = groupByDate(items);
    let html = `<div class="planner-week-view">`;
    for (let index = 0; index < 7; index += 1) {
      const day = addDays(weekStart, index);
      const key = dateKey(day);
      const dayItems = grouped[key] || [];
      html += `
        <section class="planner-week-column ${key === dateKey(new Date()) ? "is-today" : ""}" data-date="${key}">
          <div class="planner-week-date">
            <span>${escapeHtml(weekdayFormatter.format(day))}</span>
            <strong>${day.getDate()}</strong>
          </div>
          <div class="planner-week-events">
            ${dayItems.length ? dayItems.map((item) => itemMarkup(item, true)).join("") : '<div class="planner-empty-day">No plans</div>'}
          </div>
        </section>
      `;
    }
    html += `</div>`;
    calendar.innerHTML = html;

    calendar.querySelectorAll(".planner-week-column").forEach((column) => {
      const day = parseDateKey(column.dataset.date);
      column.addEventListener("dblclick", () => {
        if (column.dataset.date < dateKey(new Date())) {
          showToast("New events can only be added today or later.", true);
          return;
        }
        openCreateDialog(column.dataset.date);
      });
      attachDropTarget(column, day);
    });
    attachItemInteractions(calendar);
  }

  function renderAgenda(items) {
    if (!items.length) {
      calendar.innerHTML = `
        <div class="planner-no-items">
          <div><strong>No plans in this period</strong>Create an event or add a deadline to a task.</div>
        </div>
      `;
      return;
    }

    const grouped = groupByDate(items);
    const keys = Object.keys(grouped).sort();
    calendar.innerHTML = `
      <div class="planner-agenda">
        ${keys
          .map((key) => {
            const day = parseDateKey(key);
            return `
              <section class="planner-agenda-group">
                <div class="planner-agenda-date">
                  <strong>${escapeHtml(shortDateFormatter.format(day))}</strong>
                  <span>${escapeHtml(weekdayFormatter.format(day))}</span>
                </div>
                <div class="planner-agenda-items">
                  ${grouped[key]
                    .map(
                      (item) => `
                        <button type="button" class="planner-agenda-item ${itemClasses(item)}" data-planner-item="${escapeHtml(item.id)}">
                          <span class="planner-agenda-time">${escapeHtml(itemTime(item))}</span>
                          <span class="planner-agenda-dot"></span>
                          <span class="planner-agenda-copy">
                            <strong>${escapeHtml(item.title)}</strong>
                            <span>${escapeHtml(item.board)}</span>
                          </span>
                          <span class="planner-agenda-badge">${item.source === "task" ? escapeHtml(item.status.replace("_", " ")) : "Event"}</span>
                        </button>
                      `
                    )
                    .join("")}
                </div>
              </section>
            `;
          })
          .join("")}
      </div>
    `;
    attachItemInteractions(calendar);
  }

  function render() {
    const items = filteredItems();
    updateSummary(items);
    if (state.view === "month") renderMonth(items);
    else if (state.view === "week") renderWeek(items);
    else renderAgenda(items);
    updatePeriodLabel();
  }

  function updatePeriodLabel() {
    if (state.view === "month") {
      periodLabel.textContent = dateFormatter.format(state.anchor);
      return;
    }
    const range = currentRange();
    periodLabel.textContent = `${shortDateFormatter.format(range.start)} – ${shortDateFormatter.format(range.end)}`;
  }

  async function loadItems() {
    const range = currentRange();
    state.rangeStart = range.start;
    state.rangeEnd = range.end;
    loading.hidden = false;
    calendar.hidden = true;

    try {
      const url = new URL(app.dataset.itemsUrl, window.location.origin);
      url.searchParams.set("start", dateKey(range.start));
      url.searchParams.set("end", dateKey(range.end));
      const payload = await apiRequest(url.toString());
      state.items = payload.items || [];
      render();
    } catch (error) {
      calendar.innerHTML = `
        <div class="planner-no-items">
          <div><strong>Could not load the planner</strong>${escapeHtml(error.message)}</div>
        </div>
      `;
      showToast(error.message, true);
    } finally {
      loading.hidden = true;
      calendar.hidden = false;
    }
  }

  function setView(view) {
    state.view = view;
    localStorage.setItem("taskmaster-planner-view", view);
    viewButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.view === view);
    });
    loadItems();
  }

  function navigatePeriod(direction) {
    const next = new Date(state.anchor);
    if (state.view === "month") next.setMonth(next.getMonth() + direction);
    else if (state.view === "week") next.setDate(next.getDate() + 7 * direction);
    else next.setDate(next.getDate() + 30 * direction);
    state.anchor = next;
    loadItems();
  }

  function formatInputDate(date) {
    return dateKey(date);
  }

  function formatInputTime(date) {
    return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function openCreateDialog(date = dateKey(new Date())) {
    eventForm.reset();
    eventId.value = "";
    dialogTitle.textContent = "New event";
    deleteButton.hidden = true;
    formError.hidden = true;

    const today = dateKey(new Date());
    const allowedDate = date < today ? today : date;
    const start = parseDateKey(allowedDate);
    start.setHours(9, 0, 0, 0);
    const end = new Date(start);
    end.setHours(10, 0, 0, 0);
    startDateInput.value = formatInputDate(start);
    startDateInput.min = today;
    startTimeInput.value = formatInputTime(start);
    endDateInput.value = formatInputDate(end);
    endDateInput.min = formatInputDate(start);
    endTimeInput.value = formatInputTime(end);
    eventAllDay.checked = false;
    dialog.classList.remove("is-all-day");
    dialog.showModal();
    setTimeout(() => eventTitle.focus(), 80);
  }

  function openItem(item) {
    if (item.source === "task") {
      window.location.href = item.url;
      return;
    }

    const start = itemDate(item);
    const end = item.end ? new Date(item.end) : new Date(start.getTime() + 60 * 60 * 1000);
    eventId.value = item.item_id;
    eventTitle.value = item.title;
    eventDescription.value = item.description || "";
    eventAllDay.checked = item.all_day;
    startDateInput.value = formatInputDate(start);
    startDateInput.min = formatInputDate(start) < dateKey(new Date())
      ? formatInputDate(start)
      : dateKey(new Date());
    startTimeInput.value = formatInputTime(start);
    endDateInput.value = formatInputDate(end);
    endDateInput.min = formatInputDate(start);
    endTimeInput.value = formatInputTime(end);
    dialogTitle.textContent = "Edit event";
    deleteButton.hidden = false;
    formError.hidden = true;
    dialog.classList.toggle("is-all-day", item.all_day);
    dialog.showModal();
  }

  function eventPayload() {
    const allDay = eventAllDay.checked;
    const startTime = allDay ? "00:00" : startTimeInput.value;
    const endTime = allDay ? "23:59" : endTimeInput.value;
    return {
      title: eventTitle.value.trim(),
      description: eventDescription.value.trim(),
      all_day: allDay,
      start_at: `${startDateInput.value}T${startTime}:00`,
      end_at: `${endDateInput.value}T${endTime}:00`,
    };
  }

  async function saveEvent() {
    formError.hidden = true;
    const id = eventId.value;
    const url = id
      ? app.dataset.updateUrlTemplate.replace("__id__", id)
      : app.dataset.createUrl;

    try {
      await apiRequest(url, {
        method: "POST",
        body: JSON.stringify(eventPayload()),
      });
      dialog.close();
      showToast(id ? "Event updated." : "Event created.");
      await loadItems();
    } catch (error) {
      formError.textContent = error.message;
      formError.hidden = false;
    }
  }

  async function deleteEvent() {
    const id = eventId.value;
    if (!id || !window.confirm("Delete this event permanently?")) return;
    try {
      await apiRequest(app.dataset.deleteUrlTemplate.replace("__id__", id), {
        method: "POST",
        body: "{}",
      });
      dialog.close();
      showToast("Event deleted.");
      await loadItems();
    } catch (error) {
      formError.textContent = error.message;
      formError.hidden = false;
    }
  }

  viewButtons.forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  sourceFilters.forEach((input) => input.addEventListener("change", render));
  boardFilter.addEventListener("change", render);
  statusFilter.addEventListener("change", render);

  document.getElementById("plannerPrevious").addEventListener("click", () => navigatePeriod(-1));
  document.getElementById("plannerNext").addEventListener("click", () => navigatePeriod(1));
  document.getElementById("plannerToday").addEventListener("click", () => {
    state.anchor = new Date();
    loadItems();
  });
  document.getElementById("newPlannerEvent").addEventListener("click", () => openCreateDialog());
  document.getElementById("closePlannerDialog").addEventListener("click", () => dialog.close());
  document.getElementById("cancelPlannerEvent").addEventListener("click", () => dialog.close());
  deleteButton.addEventListener("click", deleteEvent);
  eventAllDay.addEventListener("change", () => {
    dialog.classList.toggle("is-all-day", eventAllDay.checked);
  });
  startDateInput.addEventListener("change", () => {
    endDateInput.min = startDateInput.value;
    if (endDateInput.value < startDateInput.value) {
      endDateInput.value = startDateInput.value;
    }
  });
  eventForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveEvent();
  });

  setView(state.view);
})();
