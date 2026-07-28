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

  document.querySelectorAll("[data-open-on-load]").forEach(openDialog);
})();
