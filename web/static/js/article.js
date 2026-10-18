document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const $ = (sel) => document.querySelector(sel);

  const state = $("#article-state");
  const article = $("#article");
  const id = new URLSearchParams(window.location.search).get("id");
  const favBtn = $("#fav-btn");

  // ---- Markdown → DOM ----
  // Возвращает <div> со списком детей (p/h2/h3/ul/ol).
  function renderMarkdown(text) {
    const container = document.createElement("div");

    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    let paragraph = [];
    let list = null;

    function formatInline(str) {
      let escaped = str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      escaped = escaped.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
      escaped = escaped.replace(
        /\[([^\]]+)\]\s*\(([^)\s]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
      );
      return escaped;
    }

    function flushParagraph() {
      if (paragraph.length) {
        const p = document.createElement("p");
        p.innerHTML = formatInline(paragraph.join("\n"));
        container.append(p);
        paragraph = [];
      }
    }

    function flushList() {
      if (list) { container.append(list); list = null; }
    }

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) { flushParagraph(); flushList(); continue; }

      const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph(); flushList();
        const level = heading[1].length;
        const tag = level <= 2 ? "h2" : "h3";
        const h = document.createElement(tag);
        h.textContent = heading[2];
        container.append(h);
        continue;
      }

      const bullet = trimmed.match(/^([-*]|\d+\.)\s+(.+)$/);
      if (bullet) {
        flushParagraph();
        const isOrdered = /^\d/.test(bullet[1]);
        const tag = isOrdered ? "ol" : "ul";
        if (!list || list.tagName.toLowerCase() !== tag) {
          flushList();
          list = document.createElement(tag);
        }
        const li = document.createElement("li");
        li.innerHTML = formatInline(bullet[2]);
        list.append(li);
        continue;
      }

      flushList();
      paragraph.push(trimmed);
    }
    flushParagraph();
    flushList();

    if (!container.children.length && text.trim()) {
      const p = document.createElement("p");
      p.innerHTML = formatInline(text);
      container.append(p);
    }
    return container;
  }

  // Перенос детей из одного контейнера в другой.
  // Работает и с HTMLCollection (браузер), и с массивом (mock).
  function moveChildren(from, to) {
    if (!from || !to) return;
    const kids = Array.from(from.children || []);
    if (kids.length) to.append(...kids);
  }

  // ---- Избранное ----
  async function refreshFavoriteStatus() {
    if (!favBtn) return;
    try {
      await window.ZPAuth.ready;
      if (!window.ZPAuth.isLoggedIn()) {
        favBtn.disabled = true;
        favBtn.title = "Войдите, чтобы добавить в избранное";
        favBtn.classList.remove("is-active");
        favBtn.setAttribute("aria-pressed", "false");
        return;
      }
      favBtn.disabled = false;
      const favorites = await request("cabinet/favorites?limit=100");
      const isFav = favorites.some((f) => String(f.content_item_id) === String(id));
      applyFavoriteState(isFav);
    } catch (e) {
      console.warn("Не удалось проверить статус избранного", e);
      if (favBtn) favBtn.disabled = false;
    }
  }

  function applyFavoriteState(isFav) {
    if (!favBtn) return;
    favBtn.classList.toggle("is-active", isFav);
    favBtn.setAttribute("aria-pressed", String(isFav));
    favBtn.title = isFav ? "Удалить из избранного" : "Добавить в избранное";
  }

  if (favBtn) {
    favBtn.addEventListener("click", async () => {
      if (!window.ZPAuth.isLoggedIn()) {
        window.location.href = "./login.html";
        return;
      }
      if (favBtn.dataset.busy === "1") return;
      favBtn.dataset.busy = "1";
      favBtn.disabled = true;

      const isActive = favBtn.classList.contains("is-active");
      try {
        if (isActive) {
          await request(`cabinet/favorites/${id}`, { method: "DELETE" });
          applyFavoriteState(false);
        } else {
          await request(`cabinet/favorites/${id}`, { method: "POST" });
          applyFavoriteState(true);
        }
      } catch (error) {
        console.error(error);
        if (error.status === 409 && !isActive) {
          applyFavoriteState(true);
        } else {
          const statusEl = $("#status");
          if (statusEl) statusEl.textContent = "Ошибка: " + error.message;
        }
      } finally {
        favBtn.dataset.busy = "";
        favBtn.disabled = false;
      }
    });
  }

  // ---- Рендер ----
  function render(record) {
    document.title = `${record.title} — Законпозитор`;

    const titleEl = $("#article-title");
    if (titleEl) titleEl.textContent = record.title;

    // Если в репозитории уже "Полезные материалы" — поменяйте строку ниже.
    const categoryName = record.category?.name || "Полезные материалы";
    const catEl = $("#article-category");
    if (catEl) catEl.textContent = categoryName;

    const catPath = $("#article-category-path");
    if (catPath) {
      if (record.category) {
        catPath.textContent = `/ ${categoryName}`;
        catPath.hidden = false;
      } else {
        catPath.hidden = true;
      }
    }

    // Summary
    const summaryEl = $("#article-summary");
    const summaryText = (record.summary || "").trim();
    if (summaryEl) {
      summaryEl.textContent = summaryText;
      summaryEl.hidden = !summaryText;
    }

    // Время чтения
    const chunks = record.chunks || [];
    const words = chunks.join(" ").match(/\S+/g)?.length || 0;
    const minutes = Math.max(1, Math.ceil(words / 200));
    const timeEl = $("#article-reading-time");
    if (timeEl) timeEl.textContent = `${minutes} мин. чтения`;

    const introEl = $("#article-intro");
    const introBody = $("#article-intro-body");
    const chunksEl = $("#article-chunks");
    const emptyEl = $("#article-empty");

    if (introBody) introBody.replaceChildren();
    if (chunksEl) chunksEl.replaceChildren();

    if (!chunks.length) {
      if (introEl) introEl.hidden = true;
      if (emptyEl) emptyEl.hidden = false;
    } else {
      if (introEl) introEl.hidden = !summaryText;
      if (emptyEl) emptyEl.hidden = true;

      // Первый чанк — в #article-intro-body
      const first = renderMarkdown(chunks[0]);
      if (introBody) moveChildren(first, introBody);

      // Остальные — каждый в отдельный <section> в #article-chunks
      for (let i = 1; i < chunks.length; i++) {
        const section = document.createElement("section");
        section.className = "article-chunk";
        const rendered = renderMarkdown(chunks[i]);
        moveChildren(rendered, section);
        if (chunksEl) chunksEl.append(section);
      }
    }

    if (article) article.hidden = false;
    if (state) state.hidden = true;

    refreshFavoriteStatus();
  }

  // ---- Рекомендации ----
  async function loadRelated() {
    const list = $("#related-articles-list");
    const card = $("#related-articles");
    if (!list || !card) return;
    try {
      const records = await request("public/articles?limit=4");
      list.replaceChildren();
      const filtered = records.filter((item) => String(item.id) !== String(id)).slice(0, 3);
      if (!filtered.length) { card.hidden = true; return; }
      filtered.forEach((record) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = `./article.html?id=${encodeURIComponent(record.id)}`;
        a.textContent = record.title;
        li.append(a);
        list.append(li);
      });
      card.hidden = false;
    } catch {
      card.hidden = true;
    }
  }

  // ---- Загрузка ----
  async function load() {
    if (state) {
      state.hidden = false;
      state.setAttribute("aria-busy", "true");
    }
    const retry = $("#retry-article");
    if (retry) retry.hidden = true;
    const st = $("#state-title");
    const sm = $("#state-message");
    if (st) st.textContent = "Загружаем статью…";
    if (sm) sm.textContent = "Получаем материал из базы знаний.";

    try {
      const record = await request(`public/articles/${encodeURIComponent(id)}`);
      render(record);
      loadRelated();
    } catch (error) {
      if (st) {
        st.textContent = error.status === 404
          ? "Статья не найдена" : "Не удалось загрузить статью";
      }
      if (sm) {
        sm.textContent = error.status === 404
          ? "Возможно, материал ещё не опубликован или был удалён. Другие статьи доступны в базе знаний."
          : error.message;
      }
      // Явный boolean: undefined → false → кнопка видна.
      if (retry) retry.hidden = (error.status === 404);
    } finally {
      if (state) state.setAttribute("aria-busy", "false");
    }
  }

  const retry = $("#retry-article");
  if (retry) retry.addEventListener("click", load);

  if (!id || !/^[1-9]\d*$/.test(id) || BigInt(id) > 9223372036854775807n) {
    if (state) {
      state.hidden = false;
      state.setAttribute("aria-busy", "false");
    }
    const st = $("#state-title");
    const sm = $("#state-message");
    if (st) st.textContent = "Статья не выбрана";
    if (sm) sm.textContent = "Откройте статью из базы знаний или результатов поиска.";
    if (article) article.hidden = true;
    return;
  }

  load();
});