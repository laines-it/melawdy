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
    src = src.replace(/\[([^\]]+)\]\s*\([^)\s]*\)/g, "$1");
    src = src.replace(/\[\^[^\]]+\]/g, "");
    return src;
  }

  // ---- Мини-markdown ----
  function renderInlineMarkdown(text) {
    const fragment = document.createDocumentFragment();
    const src = stripLinksAndFootnotes(text);
    appendInlineParsed(fragment, src);
    return fragment;
  }

  function appendInlineParsed(target, src) {
    let i = 0;
    while (i < src.length) {
      
      if (src[i] === "*" && src[i + 1] === "*" && src[i + 2] === "*") {
        const end = src.indexOf("***", i + 3);
        if (end !== -1) {
          const strong = document.createElement("strong");
          const em = document.createElement("em");
          appendInlineParsed(em, src.slice(i + 3, end));
          strong.appendChild(em);
          target.appendChild(strong);
          i = end + 3;
          continue;
        }
      }

      if (src[i] === "*" && src[i + 1] === "*" && src[i + 2] === "*") {
        let end = -1;
        for (let k = i + 3; k < src.length; k++) {
          if (src[k] === "*" && src[k + 1] !== "*" && src[k - 1] !== "*") {
            end = k;
            break;
          }
        }
        if (end !== -1) {
          const inner = src.slice(i + 3, end);
          const em = document.createElement("em");
          const strongEnd = inner.indexOf("**");
          if (strongEnd !== -1) {
            const strong = document.createElement("strong");
            appendInlineParsed(strong, inner.slice(0, strongEnd));
            em.appendChild(strong);
            appendInlineParsed(em, inner.slice(strongEnd + 2));
          } else {
            appendInlineParsed(em, inner);
          }
          target.appendChild(em);
          i = end + 1;
          continue;
        }
      }

      if (src[i] === "*" && src[i + 1] === "*" && src[i + 2] === "*") {
        let end = -1;
        for (let k = i + 3; k < src.length; k++) {
          if (src[k] === "*" && src[k + 1] !== "*" && src[k - 1] !== "*") {
            end = k;
            break;
          }
        }
        if (end !== -1) {
          const em = document.createElement("em");
          appendInlineParsed(em, src.slice(i + 3, end));
          target.appendChild(em);
          i = end + 1;
          continue;
        }
      }

      if (src[i] === "*" && src[i + 1] === "*" && src[i + 2] === "*") {
        let end = -1;
        for (let k = i + 3; k < src.length - 1; k++) {
          if (src[k] === "*" && src[k + 1] === "*" && src[k - 1] !== "*" && src[k + 2] !== "*") {
            end = k;
            break;
          }
        }
        if (end !== -1) {
          const strong = document.createElement("strong");
          appendInlineParsed(strong, src.slice(i + 3, end));
          target.appendChild(strong);
          i = end + 2;
          continue;
        }
      }

      if (src[i] === "`") {
        const end = src.indexOf("`", i + 1);
        if (end !== -1) {
          const code = document.createElement("code");
          code.textContent = src.slice(i + 1, end);
          target.appendChild(code);
          i = end + 1;
          continue;
        }
      }

      if (src[i] === "*" && src[i + 1] === "*") {
        const end = src.indexOf("**", i + 2);
        if (end !== -1) {
          const strong = document.createElement("strong");
          appendInlineParsed(strong, src.slice(i + 2, end)); // рекурсия
          target.appendChild(strong);
          i = end + 2;
          continue;
        }
      }

      if (src[i] === "*" && src[i + 1] !== "*") {
        const end = src.indexOf("*", i + 1);
        if (end !== -1 && src[end + 1] !== "*") {
          const em = document.createElement("em");
          appendInlineParsed(em, src.slice(i + 1, end)); // рекурсия
          target.appendChild(em);
          i = end + 1;
          continue;
        }
      }

      let j = i + 1;
      while (j < src.length && !"`*".includes(src[j])) j++;
      target.appendChild(document.createTextNode(src.slice(i, j)));
      i = j;
    }
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

  const clearBtn = document.querySelector("#search-clear");

  function syncClearButton() {
    if (clearBtn) clearBtn.hidden = !input.value;
  }

  input.addEventListener("input", syncClearButton);

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      input.value = "";
      syncClearButton();
      input.focus();

      const url = new URL(window.location.href);
      url.searchParams.delete("query");
      window.history.pushState({ query: "" }, "", url);
      runSearch("");
    });
  }

  syncClearButton();

  async function runSearch(query) {
    const currentVersion = ++searchVersion;
    status.textContent = "";
    results.hidden = false;
    if (typeof syncClearButton === "function") syncClearButton();

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
    syncClearButton();
    runSearch(query.trim());
  });
});