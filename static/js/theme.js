(function () {
  "use strict";

  const storageKey = "taskmaster-theme";
  const root = document.documentElement;

  function activeTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    root.setAttribute("data-theme", theme);
    localStorage.setItem(storageKey, theme);
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const nextTheme = theme === "dark" ? "light" : "dark";
      button.setAttribute("aria-label", `Switch to ${nextTheme} mode`);
      button.setAttribute("title", `Switch to ${nextTheme} mode`);
    });
  }

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", function () {
      setTheme(activeTheme() === "dark" ? "light" : "dark");
    });
  });

  setTheme(activeTheme());

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", function () {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;

      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
      button.setAttribute("aria-pressed", String(reveal));
    });
  });

  const profileButton = document.getElementById("profileBtn");
  const profileMenu = document.getElementById("profileDropdown");
  const profileWrap = document.getElementById("profileMenu");

  if (profileButton && profileMenu && profileWrap) {
    const closeProfile = function () {
      profileMenu.hidden = true;
      profileButton.setAttribute("aria-expanded", "false");
    };

    profileButton.addEventListener("click", function (event) {
      event.stopPropagation();
      profileMenu.hidden = !profileMenu.hidden;
      profileButton.setAttribute("aria-expanded", String(!profileMenu.hidden));
    });

    document.addEventListener("click", function (event) {
      if (!profileWrap.contains(event.target)) closeProfile();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeProfile();
    });
  }

  const notificationButton = document.getElementById("notificationBtn");
  const notificationMenu = document.getElementById("notificationDropdown");
  const notificationWrap = document.getElementById("notificationMenu");

  if (notificationButton && notificationMenu && notificationWrap) {
    const closeNotifications = function () {
      notificationMenu.hidden = true;
      notificationButton.setAttribute("aria-expanded", "false");
    };

    notificationButton.addEventListener("click", function (event) {
      event.stopPropagation();
      notificationMenu.hidden = !notificationMenu.hidden;
      notificationButton.setAttribute("aria-expanded", String(!notificationMenu.hidden));
    });

    document.addEventListener("click", function (event) {
      if (!notificationWrap.contains(event.target)) closeNotifications();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeNotifications();
    });
  }
})();
