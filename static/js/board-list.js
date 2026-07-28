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

  const editDialog = document.getElementById("edit-board-dialog");
  const editForm = document.getElementById("edit-board-form");
  const editName = document.getElementById("edit-board-name");
  const editDescription = document.getElementById("edit-board-description");

  document.querySelectorAll("[data-edit-board]").forEach((button) => {
    button.addEventListener("click", () => {
      editForm.action = button.dataset.boardAction;
      editName.value = button.dataset.boardName;
      editDescription.value = button.dataset.boardDescription;
      openDialog(editDialog);
      editName.focus();
    });
  });

  const deleteDialog = document.getElementById("delete-board-dialog");
  const deleteForm = document.getElementById("delete-board-form");
  const deleteName = document.getElementById("delete-board-name");

  document.querySelectorAll("[data-delete-board]").forEach((button) => {
    button.addEventListener("click", () => {
      deleteForm.action = button.dataset.boardAction;
      deleteName.textContent = button.dataset.boardName;
      openDialog(deleteDialog);
    });
  });

  document.querySelectorAll("[data-open-on-load]").forEach(openDialog);
})();
