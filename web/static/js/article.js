document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const state = document.querySelector("#article-state");
  const retry = document.querySelector("#retry-article");
  const article = document.querySelector("#article");
  const id = new URLSearchParams(window.location.search).get("id");

  function node(tag, text) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  // Render text and a small set of block markers without interpreting stored HTML.
  function renderChunk(target, body) {
    let paragraph = [];
    let list = null;
    function flush() {
      if (paragraph.length) target.append(node("p", paragraph.join("\n")));
      paragraph = [];
    }
    for (const line of body.replace(/\r\n?/g, "\n").split("\n")) {
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      const bullet = line.match(/^\s*([-*]|\d+\.)\s+(.+)$/);
      if (!line.trim() || heading || bullet) flush();
      if (heading) {
        list = null;
        target.append(node(line.startsWith("###") ? "h3" : "h2", heading[1]));
      } else if (bullet) {
        const tag = /^\d/.test(bullet[1]) ? "ol" : "ul";
        if (!list || list.tagName.toLowerCase() !== tag) {
          list = node(tag);
          target.append(list);
        }
        list.append(node("li", bullet[2]));
      } else {
        list = null;
        if (line.trim()) paragraph.push(line);
      }
    }
    flush();
  }

  function render(record) {
    document.title = `${record.title} — Законпозитор`;
    document.querySelector("#article-title").textContent = record.title;
    const summary = document.querySelector("#article-summary");
    summary.textContent = record.summary || "";
    summary.hidden = !record.summary;
    const category = record.category?.name;
    document.querySelector("#article-category").textContent = category || "База знаний";
    const categoryPath = document.querySelector("#article-category-path");
    categoryPath.textContent = category ? `/ ${category}` : "";
    categoryPath.hidden = !category;

    const chunks = record.chunks || [];
    const words = chunks.join(" ").match(/\S+/g)?.length || 0;
    document.querySelector("#article-reading-time").textContent = `${Math.max(1, Math.ceil(words / 200))} мин. чтения`;
    const intro = document.querySelector("#article-intro");
    const introBody = document.querySelector("#article-intro-body");
    const body = document.querySelector("#article-chunks");
    introBody.replaceChildren();
    body.replaceChildren();
    intro.hidden = !chunks.length;
    document.querySelector("#article-empty").hidden = Boolean(chunks.length);
    chunks.forEach((text, index) => {
      if (index === 0) {
        renderChunk(introBody, text);
      } else {
        const section = node("section");
        section.className = "article-chunk";
        renderChunk(section, text);
        body.append(section);
      }
    });
    article.hidden = false;
    state.hidden = true;
  }

  async function loadRelated() {
    // Recommendations are optional; their failure must not hide the requested article.
    try {
      const records = await request("public/articles?limit=4");
      const list = document.querySelector("#related-articles-list");
      list.replaceChildren();
      for (const record of records.filter((item) => String(item.id) !== id).slice(0, 3)) {
        const item = node("li");
        const link = node("a", record.title);
        link.href = `./article.html?id=${encodeURIComponent(record.id)}`;
        item.append(link);
        list.append(item);
      }
      document.querySelector("#related-articles").hidden = !list.children.length;
    } catch {
      document.querySelector("#related-articles").hidden = true;
    }
  }

  async function load() {
    state.hidden = false;
    state.setAttribute("aria-busy", "true");
    retry.hidden = true;
    document.querySelector("#state-title").textContent = "Загружаем статью…";
    document.querySelector("#state-message").textContent = "Получаем материал из базы знаний.";
    try {
      render(await request(`public/articles/${encodeURIComponent(id)}`));
      await loadRelated();
    } catch (error) {
      document.querySelector("#state-title").textContent = error.status === 404
        ? "Статья не найдена" : "Не удалось загрузить статью";
      document.querySelector("#state-message").textContent = error.status === 404
        ? "Возможно, материал ещё не опубликован или был удалён. Другие статьи доступны в базе знаний."
        : error.message;
      retry.hidden = error.status === 404;
    } finally {
      state.setAttribute("aria-busy", "false");
    }
  }

  retry.addEventListener("click", load);
  if (!id || !/^[1-9]\d*$/.test(id) || BigInt(id) > 9223372036854775807n) {
    state.setAttribute("aria-busy", "false");
    document.querySelector("#state-title").textContent = "Статья не выбрана";
    document.querySelector("#state-message").textContent = "Откройте статью из базы знаний или результатов поиска.";
    return;
  }
  load();
});
