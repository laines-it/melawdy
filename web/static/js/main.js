document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".site-header");
  const toggle = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-main-nav]");
  const form = document.querySelector("#question-form");
  const input = document.querySelector("#question");
  const answerStatus = document.querySelector("#answer-status");

  const syncHeader = () => header?.classList.toggle("is-scrolled", window.scrollY > 8);
  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  toggle?.addEventListener("click", () => {
    const open = header.classList.toggle("menu-open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  nav?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
    header.classList.remove("menu-open");
    toggle?.setAttribute("aria-expanded", "false");
  }));
  document.querySelectorAll("[data-question]").forEach((chip) => chip.addEventListener("click", () => {
    input.value = chip.dataset.question;
    input.focus();
  }));

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Отправляем вопрос…";
    try {
      const response = await fetch("/api/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: input.value.trim() }),
      });
      if (!response.ok) throw new Error("API unavailable");
      const result = await response.json();
      answerStatus.textContent = result.message;
    } catch {
      answerStatus.textContent = "Сервис временно недоступен. Попробуйте позже.";
    }
    button.textContent = original;
    button.disabled = false;
  });
});
