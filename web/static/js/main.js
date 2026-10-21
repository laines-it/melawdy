document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const status = document.querySelector("#status");
  const R = window.ZPRoutes;

  function message(error) {
    if (status) status.textContent = error.message;
    else console.error(error);
  }
  function node(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function articleLink(id, title) {
    const link = node("a", title);
    link.href = R.article(id);
    return link;
  }

  async function loadFaq() {
    const list = document.querySelector("#faq-list");
    if (!list) return;
    const records = await request("public/faq");
    list.replaceChildren();
    if (!records.length) list.append(node("p", "Вопросы пока не опубликованы."));
    for (const record of records) {
      const card = document.createElement("details");
      card.className = "faq-card";
      const summary = node("summary", record.question);
      summary.className = "faq-question";
      const answer = node("p", record.answer);
      answer.className = "faq-answer";
      card.append(summary, answer);
      if (record.content_slug || record.content_item_id) {
        const linkText = record.link_title || record.content_title || "Читать материал →";
        const link = node("a", linkText);
        link.href = R.article(record.content_slug || record.content_item_id);
        card.append(link);
      }
      list.append(card);
    }
  }

  const searchForm = document.querySelector("#search-form");
  if (searchForm) {
    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const query = document.querySelector("#search-query").value.trim();
      if (!query) return;
      window.location.href = `${R.search}?query=${encodeURIComponent(query)}`;
    });
  }

  // Крестик очистки в поисковом поле главной
  const searchInput = document.querySelector("#search-query");
  const searchClear = document.querySelector("#search-clear");

  if (searchInput && searchClear) {
    const updateClearVisibility = () => {
      searchClear.hidden = searchInput.value.trim() === "";
    };

    updateClearVisibility();
    searchInput.addEventListener("input", updateClearVisibility);

    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      updateClearVisibility();
      searchInput.focus();
    });
  }

  loadFaq().catch(message);
});