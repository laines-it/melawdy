document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const form = document.querySelector("#search-form");
  const input = document.querySelector("#search-query");
  const status = document.querySelector("#status");
  const results = document.querySelector("#search-results");
  let searchVersion = 0;

  // Эвристика: бэк возвращает { article_id, title, body }.
  // Если в будущем появится type/type_label/inside_label — используем их.
  function labelFor(record) {
    if (record.type_label) return record.type_label;
    const map = {
      article: "Статья",
      template: "Шаблон",
      faq: "Вопрос",
      survey: "Опрос",
    };
    if (record.type && map[record.type]) return map[record.type];
    return record.article_id ? "Статья" : "Материал";
  }

  function insideFor(record) {
    if (record.inside_label) return record.inside_label;
    if (Number.isFinite(record.inside_count) && record.inside_count > 0) {
      return `Что внутри (${record.inside_count})`;
    }
    return "Что внутри →";
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function articleHref(record) {
    if (!record.article_id) return null;
    return `./article.html?id=${encodeURIComponent(record.article_id)}`;
  }

  function renderCard(record, index) {
    const href = articleHref(record);
    const card = element("article", "search-card" + (index === 0 ? " search-card--featured" : ""));
    card.dataset.index = String(index);

    const head = element("div", "search-card-head");
    head.append(element("p", "search-card-label", labelFor(record)));

    const arrow = element("a", "search-card-arrow", "↗");
    if (href) {
      arrow.href = href;
      arrow.setAttribute("aria-label", `Открыть: ${record.title}`);
    } else {
      arrow.setAttribute("aria-hidden", "true");
    }
    head.append(arrow);

    const title = element("h2", "search-card-title");
    if (href) {
      const titleLink = element("a", null, record.title || "Без названия");
      titleLink.href = href;
      title.append(titleLink);
    } else {
      title.textContent = record.title || "Без названия";
    }

    const body = element("p", "search-card-body", record.body || "");
    if (record.body) body.title = record.body;

    const foot = element("div", "search-card-foot");
    if (href) {
      const inside = element("a", "search-card-inside", insideFor(record));
      inside.href = href;
      foot.append(inside);
    } else {
      foot.append(element("span", "search-card-inside", insideFor(record)));
    }

    card.append(head, title, body, foot);
    return card;
  }

  function renderEmpty(query) {
    const box = element("div", "search-empty");
    box.append(element("strong", null, "Ничего не найдено"));
    box.append(document.createTextNode(
      query
        ? `По запросу «${query}» материалов не найдено. Попробуйте переформулировать.`
        : "Введите вопрос, чтобы найти материалы."
    ));
    results.replaceChildren(box);
  }

  async function runSearch(query) {
    const currentVersion = ++searchVersion;
    status.textContent = "";
    if (!query) {
      results.hidden = true;
      results.replaceChildren();
      return;
    }
    results.hidden = false;
    status.textContent = "Поиск…";
    try {
      const records = await request(`public/search?query=${encodeURIComponent(query)}`);
      if (currentVersion !== searchVersion) return;
      if (!records.length) {
        status.textContent = "";
        renderEmpty(query);
        return;
      }
      status.textContent = "";
      const fragment = document.createDocumentFragment();
      records.forEach((record, index) => fragment.append(renderCard(record, index)));
      results.replaceChildren(fragment);
    } catch (error) {
      if (currentVersion !== searchVersion) return;
      status.textContent = error.message;
      results.hidden = true;
      results.replaceChildren();
    }
  }

  // Сабмит: обновляем URL (без перезагрузки) и запускаем поиск.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = input.value.trim();
    const url = new URL(window.location.href);
    if (query) url.searchParams.set("query", query);
    else url.searchParams.delete("query");
    window.history.pushState({ query }, "", url);
    runSearch(query);
  });

  // Deep-link: если пришли с index.html с ?query=... — сразу ищем.
  const initialQuery = new URLSearchParams(window.location.search).get("query") || "";
  if (initialQuery) {
    input.value = initialQuery;
    runSearch(initialQuery.trim());
  }

  // Кнопки «Назад/Вперёд» браузера — синхронизируем состояние.
  window.addEventListener("popstate", () => {
    const query = new URLSearchParams(window.location.search).get("query") || "";
    input.value = query;
    runSearch(query.trim());
  });
});