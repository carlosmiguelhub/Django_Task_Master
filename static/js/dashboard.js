(() => {
  "use strict";

  const launcher = document.getElementById("aiDailyPlanLauncher");
  const dialog = document.getElementById("aiDailyPlanDialog");
  if (!launcher || !dialog) return;

  const states = Array.from(dialog.querySelectorAll("[data-ai-state]"));
  const loadingSteps = Array.from(dialog.querySelectorAll(".tm-ai-loading-steps span"));
  const loadingTitle = dialog.querySelector("[data-ai-loading-title]");
  const loadingDetail = dialog.querySelector("[data-ai-loading-detail]");
  const loadingTime = dialog.querySelector("[data-ai-loading-time]");
  const chatForm = dialog.querySelector("[data-ai-chat-form]");
  const chatInput = dialog.querySelector("[data-ai-chat-input]");
  const chatMessages = dialog.querySelector("[data-ai-chat-messages]");
  const chatSuggestions = dialog.querySelector("[data-ai-chat-suggestions]");
  const chatCount = dialog.querySelector("[data-ai-chat-count]");
  const csrfToken = dialog.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  let loadingInterval = null;
  let loadingTimer = null;
  let requestController = null;
  let chatController = null;
  let isGenerating = false;
  let isChatting = false;

  const showState = (name) => {
    states.forEach((state) => {
      state.hidden = state.dataset.aiState !== name;
    });
    dialog.querySelector(".tm-ai-modal-body")?.scrollTo({ top: 0 });
  };

  const stopLoadingAnimation = () => {
    if (loadingInterval) window.clearInterval(loadingInterval);
    if (loadingTimer) window.clearInterval(loadingTimer);
    loadingInterval = null;
    loadingTimer = null;
  };

  const startLoadingAnimation = () => {
    const titles = [
      "Reviewing your deadlines…",
      "Balancing priority and workload…",
      "Designing your focus plan…",
    ];
    const details = [
      "Checking urgency, status, and the work closest to its deadline.",
      "Making room around your calendar and current commitments.",
      "Turning the strongest priorities into an achievable sequence.",
    ];
    const startedAt = Date.now();
    let step = 0;
    loadingSteps.forEach((item, index) => {
      item.classList.toggle("active", index === 0);
      item.classList.remove("complete");
    });
    loadingTitle.textContent = titles[0];
    loadingDetail.textContent = details[0];
    loadingTime.textContent = "Working securely…";
    stopLoadingAnimation();
    loadingInterval = window.setInterval(() => {
      step = (step + 1) % titles.length;
      loadingTitle.textContent = titles[step];
      loadingDetail.textContent = details[step];
      loadingSteps.forEach((item, index) => {
        item.classList.toggle("active", index === step);
        item.classList.toggle("complete", index < step);
      });
    }, 1700);
    loadingTimer = window.setInterval(() => {
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      loadingTime.textContent = `${seconds}s elapsed · Your tasks remain unchanged`;
    }, 1000);
  };

  const setGenerating = (active) => {
    isGenerating = active;
    dialog.toggleAttribute("aria-busy", active);
    launcher.classList.toggle("is-working", active);
    dialog
      .querySelectorAll("[data-ai-generate], [data-ai-regenerate], [data-ai-retry]")
      .forEach((button) => {
        button.disabled = active;
      });
  };

  const appendChatMessage = (role, message, options = {}) => {
    const item = document.createElement("div");
    item.className = `tm-ai-message ${role}`;
    if (options.loading) item.classList.add("is-typing");
    if (options.error) item.classList.add("is-error");

    const avatar = document.createElement("span");
    avatar.className = "tm-ai-message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = role === "user" ? "You" : "AI";

    const body = document.createElement("div");
    const author = document.createElement("strong");
    author.textContent = role === "user" ? "You" : "Task Master AI";
    const copy = document.createElement("p");
    copy.textContent = message;
    body.append(author, copy);
    item.append(avatar, body);
    chatMessages.append(item);
    chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: "smooth" });
    return item;
  };

  const renderChatSuggestions = (suggestions = []) => {
    chatSuggestions.replaceChildren();
    suggestions.forEach((suggestion) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = suggestion;
      chatSuggestions.append(button);
    });
    chatSuggestions.hidden = suggestions.length === 0;
  };

  const setChatting = (active) => {
    isChatting = active;
    chatInput.disabled = active;
    chatForm.querySelector("[data-ai-chat-send]").disabled = active;
    chatForm.classList.toggle("is-busy", active);
  };

  const resizeChatInput = () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${Math.min(chatInput.scrollHeight, 120)}px`;
    chatCount.textContent = `${chatInput.value.length} / 600`;
  };

  const sendChatMessage = async (suggestedQuestion = "") => {
    if (isChatting) return;
    const question = (suggestedQuestion || chatInput.value).trim();
    if (!question) {
      chatInput.focus();
      return;
    }

    appendChatMessage("user", question);
    chatInput.value = "";
    resizeChatInput();
    chatSuggestions.hidden = true;
    const typingMessage = appendChatMessage("assistant", "Thinking through your workspace…", {
      loading: true,
    });
    const controller = new AbortController();
    chatController = controller;
    setChatting(true);

    try {
      const response = await fetch(dialog.dataset.chatUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Workspace chat is unavailable.");
      typingMessage.remove();
      appendChatMessage("assistant", payload.answer);
      renderChatSuggestions(payload.suggestions);
    } catch (error) {
      typingMessage.remove();
      if (error.name === "AbortError") return;
      appendChatMessage(
        "assistant",
        error.message || "I couldn’t answer that just now. Please try again.",
        { error: true },
      );
    } finally {
      if (chatController === controller) {
        chatController = null;
        setChatting(false);
        chatInput.focus();
      }
    }
  };

  const makeEmptyMessage = (message) => {
    const paragraph = document.createElement("p");
    paragraph.className = "tm-ai-result-empty";
    paragraph.textContent = message;
    return paragraph;
  };

  const renderPlan = (plan, cached) => {
    dialog.querySelector("[data-ai-headline]").textContent = plan.headline;
    dialog.querySelector("[data-ai-summary]").textContent = plan.summary;
    dialog.querySelector("[data-ai-encouragement]").textContent = plan.encouragement;
    dialog.querySelector("[data-ai-cache-label]").textContent = cached
      ? "Reused your recent plan. Regenerate for a fresh review."
      : "Generated from your current workspace. No tasks were changed.";

    const priorities = dialog.querySelector("[data-ai-priorities]");
    priorities.replaceChildren();
    priorities.className = "tm-ai-priority-list";
    if (!plan.priorities.length) {
      priorities.append(makeEmptyMessage("No unfinished task needs prioritizing."));
    }
    plan.priorities.forEach((priority, index) => {
      const item = document.createElement("a");
      item.className = "tm-ai-priority-item";
      item.href = priority.url;

      const rank = document.createElement("b");
      rank.textContent = String(index + 1).padStart(2, "0");

      const copy = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = priority.title;
      const reason = document.createElement("small");
      reason.textContent = `${priority.reason} ${priority.action}`.trim();
      copy.append(title, reason);

      const arrow = document.createElement("i");
      arrow.textContent = "›";
      item.append(rank, copy, arrow);
      priorities.append(item);
    });

    const schedule = dialog.querySelector("[data-ai-schedule]");
    schedule.replaceChildren();
    if (!plan.schedule.length) {
      schedule.append(makeEmptyMessage("Your calendar is open for flexible focus."));
    }
    plan.schedule.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "tm-ai-schedule-item";
      const time = document.createElement("time");
      time.textContent = entry.time;
      const task = document.createElement("strong");
      task.textContent = entry.task;
      const duration = document.createElement("span");
      duration.textContent = entry.duration;
      item.append(time, task, duration);
      schedule.append(item);
    });

    const risks = dialog.querySelector("[data-ai-risks]");
    risks.replaceChildren();
    if (!plan.risks.length) {
      risks.append(makeEmptyMessage("No immediate workload risks detected."));
    }
    plan.risks.forEach((risk) => {
      const item = document.createElement("li");
      item.textContent = risk;
      risks.append(item);
    });

    showState("results");
  };

  const generatePlan = async (refresh = false) => {
    if (isGenerating) return;
    const controller = new AbortController();
    requestController = controller;
    setGenerating(true);
    showState("loading");
    startLoadingAnimation();
    const minimumAnimation = new Promise((resolve) => window.setTimeout(resolve, 2100));

    try {
      const request = fetch(dialog.dataset.planUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ refresh }),
        signal: controller.signal,
      });
      const [response] = await Promise.all([request, minimumAnimation]);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Daily Plan is unavailable.");
      renderPlan(payload.plan, payload.cached);
    } catch (error) {
      if (error.name === "AbortError") return;
      dialog.querySelector("[data-ai-error-message]").textContent =
        error.message || "Please try again in a moment.";
      showState("error");
    } finally {
      if (requestController === controller) {
        requestController = null;
        stopLoadingAnimation();
        setGenerating(false);
      }
    }
  };

  launcher.addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    showState("intro");
  });

  dialog.querySelectorAll("[data-ai-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  dialog.querySelector("[data-ai-generate]")?.addEventListener("click", () => {
    generatePlan(false);
  });
  dialog.querySelector("[data-ai-regenerate]")?.addEventListener("click", () => {
    generatePlan(true);
  });
  dialog.querySelector("[data-ai-retry]")?.addEventListener("click", () => {
    generatePlan(false);
  });
  dialog.querySelectorAll("[data-ai-open-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      showState("chat");
      window.setTimeout(() => chatInput.focus(), 80);
    });
  });
  dialog.querySelector("[data-ai-chat-back]")?.addEventListener("click", () => {
    showState("intro");
  });

  chatForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendChatMessage();
  });
  chatInput?.addEventListener("input", resizeChatInput);
  chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChatMessage();
    }
  });
  chatSuggestions?.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button) sendChatMessage(button.textContent);
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    requestController?.abort();
    chatController?.abort();
    stopLoadingAnimation();
    setGenerating(false);
    setChatting(false);
  });
  resizeChatInput();
})();
