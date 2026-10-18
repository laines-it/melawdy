document.addEventListener("DOMContentLoaded", () => {
  const checkboxes = document.querySelectorAll(".checklist-checkbox");
  if (!checkboxes.length) return;

  // Ключ для хранения — можно привязать к ID статьи, чтобы чек-листы не пересекались
  const articleId = new URLSearchParams(window.location.search).get("id") || "default";
  const storageKey = `checklist_${articleId}`;

  // Восстанавливаем состояние
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(storageKey)) || {};
  } catch {}

  checkboxes.forEach((checkbox, index) => {
    if (saved[index]) checkbox.checked = true;

    checkbox.addEventListener("change", () => {
      saved[index] = checkbox.checked;
      try {
        localStorage.setItem(storageKey, JSON.stringify(saved));
      } catch {}
    });
  });
});