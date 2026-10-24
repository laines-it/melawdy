document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const form = document.querySelector("#search-form");
  const input = document.querySelector("#search-query");
  const status = document.querySelector("#status");
  const results = document.querySelector("#search-results");
  let searchVersion = 0;

  // ---- Убираем ссылки и сноски, оставляя текст ----
  function stripLinksAndFootnotes(text) {
    let src = String(text ?? "");
    // [текст](ссылка) -> текст
    src = src.replace(/\[([^\]]+)\]\s*\([^)\s]*\)/g, "$1");
    // [^N] -> пусто
    src = src.replace(/\[\^[^\]]+\]/g, "");
    return src;
  }

  // ---- Мини-markdown → DOM (inline) без ссылок и сносок ----
  function renderInlineMarkdown(text) {
    const fragment = document.createDocumentFragment();
    const src = stripLinksAndFootnotes(text);

    const tokens = /\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|`([^`]+)`/g;
    let offset = 0;
    for (const match of src.matchAll(tokens)) {
      fragment.append(document.createTextNode(src.slice(offset, match.index)));
      if (match[1] !== undefined || match[2] !== undefined) {
        const node = document.createElement(match[1] !== undefined ? "strong" : "em");
        node.textContent = match[1] ?? match[2];
        fragment.append(node);
      } else if (match[3] !== undefined) {
        const code = document.createElement("code");
        code.textContent = match[3];
        fragment.append(code);
      }
      offset = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(src.slice(offset)));
    return fragment;
  }

  function labelFor(record) {
    if (!record || typeof record !== "object") return "Материал";
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
    if (record && record.inside_label) return record.inside_label;
    if (record && Number.isFinite(record.inside_count) && record.inside_count > 0) {
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
    if (!record) return null;
    if (record.slug) return `/article/${encodeURIComponent(record.slug)}`;
    if (record.article_id) return `./article.html?id=${encodeURIComponent(record.article_id)}`;
    return null;
  }

  function renderCard(record, index) {
    if (!record || typeof record !== "object") record = {};
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

    // Заголовок — markdown-inline (без ссылок и сносок)
    const title = element("h2", "search-card-title");
    if (href) {
      const titleLink = element("a");
      titleLink.href = href;
      titleLink.replaceChildren(renderInlineMarkdown(record.title || "Без названия"));
      title.append(titleLink);
    } else {
      title.replaceChildren(renderInlineMarkdown(record.title || "Без названия"));
    }

    // Описание — markdown-inline (без ссылок и сносок)
    const body = element("p", "search-card-body");
    body.replaceChildren(renderInlineMarkdown(record.body || ""));
    if (record.body) body.title = stripLinksAndFootnotes(record.body);

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
        : "Пока нет опубликованных статей. Загляните позже."
    ));
    results.replaceChildren(box);
  }

  async function runSearch(query) {
    const currentVersion = ++searchVersion;
    status.textContent = "";
    results.hidden = false;

    const isBrowse = !query;
    if (!isBrowse) status.textContent = "Поиск…";

    try {
      let records;
      if (isBrowse) {
        const raw = await request("public/articles?limit=50&offset=0");
        const articles = Array.isArray(raw) ? raw : (raw?.items || []);
        records = articles.map((r) => ({
          article_id: r.id,
          slug: r.slug,
          title: r.title,
          body: r.summary || r.body || "",
          type: "article",
        }));
      } else {
        const raw = await request(`public/search?query=${encodeURIComponent(query)}`);
        records = Array.isArray(raw) ? raw : (raw?.items || []);
      }
      if (currentVersion !== searchVersion) return;

      const list = Array.isArray(records) ? records.filter(Boolean) : [];
      if (!list.length) {
        status.textContent = "";
        renderEmpty(query);
        return;
      }

      status.textContent = "";
      const fragment = document.createDocumentFragment();
      list.forEach((record, index) => fragment.append(renderCard(record, index)));
      results.replaceChildren(fragment);
    } catch (error) {
      if (currentVersion !== searchVersion) return;
      status.textContent = error.message;
      results.hidden = true;
      results.replaceChildren();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = input.value.trim();
    const url = new URL(window.location.href);
    if (query) url.searchParams.set("query", query);
    else url.searchParams.delete("query");
    window.history.pushState({ query }, "", url);
    runSearch(query);
  });

  const initialQuery = new URLSearchParams(window.location.search).get("query") || "";
  if (initialQuery) input.value = initialQuery;
  runSearch(initialQuery.trim());

  window.addEventListener("popstate", () => {
    const query = new URLSearchParams(window.location.search).get("query") || "";
    input.value = query;
    runSearch(query.trim());
  });
});