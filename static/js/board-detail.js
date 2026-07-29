(() => {
  const openDialog = (dialog) => {
    if (dialog && !dialog.open) dialog.showModal();
  };

  document.querySelectorAll("[data-dialog-open]").forEach((button) => {
    button.addEventListener("click", () => {
      openDialog(document.getElementById(button.dataset.dialogOpen));
    });
  });

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog")?.close());
  });

  document.querySelectorAll(".board-dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  const dueDate = document.getElementById("id_due_date");
  if (dueDate) {
    const localToday = new Date();
    localToday.setMinutes(localToday.getMinutes() - localToday.getTimezoneOffset());
    dueDate.min = localToday.toISOString().slice(0, 10);
  }

  const taskGrid = document.querySelector("[data-task-grid]");
  const taskViewButtons = document.querySelectorAll("[data-task-view]");

  const setTaskView = (view) => {
    const useListView = view === "list";
    taskGrid?.classList.toggle("is-list-view", useListView);

    taskViewButtons.forEach((button) => {
      const isActive = button.dataset.taskView === view;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
  };

  if (taskGrid && taskViewButtons.length) {
    let savedTaskView = "board";
    try {
      savedTaskView = localStorage.getItem("taskmaster-task-view") || "board";
    } catch {
      // Keep the default view when storage is unavailable.
    }
    setTaskView(savedTaskView === "list" ? "list" : "board");

    taskViewButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const view = button.dataset.taskView;
        setTaskView(view);
        try {
          localStorage.setItem("taskmaster-task-view", view);
        } catch {
          // The selected view still works for the current page.
        }
      });
    });
  }

  const formatDuration = (milliseconds) => {
    const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (days) return `${days}d ${hours}h`;
    if (hours) return `${hours}h ${minutes}m`;
    if (minutes) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
  };

  const taskTimers = Array.from(document.querySelectorAll("[data-task-timer]"))
    .map((card) => ({
      card,
      createdAt: new Date(card.dataset.createdAt).getTime(),
      dueAt: new Date(card.dataset.dueAt).getTime(),
      bar: card.querySelector("[data-timeline-bar]"),
      track: card.querySelector(".kanban-progress-track"),
      progressLabel: card.querySelector("[data-progress-label]"),
      timeLeft: card.querySelector("[data-time-left]"),
      dueStatus: card.querySelector("[data-due-status]"),
      dueRow: card.querySelector(".kanban-due"),
    }))
    .filter((timer) => Number.isFinite(timer.createdAt) && Number.isFinite(timer.dueAt));

  const updateTaskTimers = () => {
    const now = Date.now();

    taskTimers.forEach((timer) => {
      const duration = timer.dueAt - timer.createdAt;
      const elapsed = now - timer.createdAt;
      const percent = duration > 0
        ? Math.max(0, Math.min(100, (elapsed / duration) * 100))
        : 100;
      const overdue = now >= timer.dueAt;
      const roundedPercent = Math.round(percent);

      timer.bar.style.width = `${percent}%`;
      timer.track.setAttribute("aria-valuenow", String(roundedPercent));
      timer.progressLabel.textContent = `${roundedPercent}% elapsed`;
      timer.timeLeft.textContent = overdue
        ? `Overdue by ${formatDuration(now - timer.dueAt)}`
        : `${formatDuration(timer.dueAt - now)} left`;
      timer.card.classList.toggle("is-overdue", overdue);
      timer.dueRow?.classList.toggle("danger", overdue);
      if (timer.dueStatus) timer.dueStatus.textContent = overdue ? "Overdue · " : "";
    });
  };

  if (taskTimers.length) {
    updateTaskTimers();
    window.setInterval(updateTaskTimers, 1000);
  }

  document.querySelectorAll("[data-open-on-load]").forEach(openDialog);
})();
