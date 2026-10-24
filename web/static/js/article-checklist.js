document.addEventListener("DOMContentLoaded", () => {
  const chunks = document.querySelector("#article-chunks");
  if (!chunks) return;
  document.addEventListener("article-rendered", () => {
    initChecklists();
  });
  if (chunks.querySelector(".task-list-item input[type='checkbox']")) {
    initChecklists();
  }

  /* ----- helpers ----- */

  function getArticleKey() {
    const params = new URLSearchParams(window.location.search);
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const slug = pathParts[0] === "article" ? decodeURIComponent(pathParts[1] || "") : "";
    return slug || params.get("id") || "default";
  }

  function hashText(text) {
    const src = String(text ?? "").trim();
    let h = 0;
    for (let i = 0; i < src.length; i++) {
      h = (h * 31 + src.charCodeAt(i)) | 0;
    }
    return Math.abs(h).toString(36);
  }

  function loadSaved(storageKey) {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function persist(storageKey, saved) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(saved));
    } catch (e) {
      console.warn("Не удалось сохранить состояние чек-листа:", e);
    }
  }

  /* ----------------------- init ----------------------- */

  function initChecklists() {
    const checkboxes = chunks.querySelectorAll(".task-list-item input[type='checkbox']");
    if (!checkboxes.length) return;

    const storageKey = `checklist_${getArticleKey()}`;
    const saved = loadSaved(storageKey);

    checkboxes.forEach((checkbox, index) => {
      const item = checkbox.closest(".task-list-item");
      const textEl = item?.querySelector(".task-text");
      const text = textEl?.textContent ?? "";

      // Ключ пункта: хеш текста, а при пустом тексте — fallback на индекс
      const itemKey = text ? `t_${hashText(text)}` : `i_${index}`;

      // Восстановление состояния
      if (saved[itemKey]) {
        checkbox.checked = true;
        item?.classList.add("is-completed");
      } else {
        checkbox.checked = false;
        item?.classList.remove("is-completed");
      }

      // Если обработчик уже навешан — не дублируем
      if (checkbox.dataset.checklistBound === "1") return;
      checkbox.dataset.checklistBound = "1";

      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          saved[itemKey] = true;
        } else {
          delete saved[itemKey];
        }
        persist(storageKey, saved);

        const li = checkbox.closest(".task-list-item");
        if (li) li.classList.toggle("is-completed", checkbox.checked);
      });
    });
  }
});