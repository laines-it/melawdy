document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const $ = (sel) => document.querySelector(sel);

  const state = $("#article-state");
  const article = $("#article");
  const favBtn = $("#fav-btn");
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const slugFromPath = pathParts[0] === "article" ? decodeURIComponent(pathParts[1] || "") : "";
  const params = new URLSearchParams(window.location.search);
  const idFromQuery = params.get("id");
  const slug = slugFromPath || null;
  const id = idFromQuery || null;

  // Для избранного нужен числовой id статьи — узнаём его после загрузки.
  let resolvedId = null;

  // ---- helpers ----
  function clear(el) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  }
  function setText(el, text) {
    if (el) el.textContent = String(text ?? "");
  }
  function show(el) {
    if (!el) return;
    el.hidden = false;
    if (typeof el.removeAttribute === "function") el.removeAttribute("hidden");
  }
  function hide(el) {
    if (!el) return;
    el.hidden = true;
    if (typeof el.setAttribute === "function") el.setAttribute("hidden", "");
  }
  function addClass(el, cls) {
    if (!el) return;
    if (el.classList && typeof el.classList.add === "function") el.classList.add(cls);
    else el.className = ((el.className || "") + " " + cls).trim();
  }
  function removeClass(el, cls) {
    if (!el) return;
    if (el.classList && typeof el.classList.remove === "function") el.classList.remove(cls);
    else el.className = (el.className || "").split(/\s+/).filter((c) => c && c !== cls).join(" ");
  }
  function hasClass(el, cls) {
    if (!el) return false;
    if (el.classList && typeof el.classList.contains === "function") return el.classList.contains(cls);
    return (el.className || "").split(/\s+/).includes(cls);
  }
  function articleHref(record) {
    if (!record || typeof record !== "object") return null;
    if (record.slug) return `/article/${encodeURIComponent(record.slug)}`;
    if (record.id != null) return `./article.html?id=${encodeURIComponent(record.id)}`;
    return null;
  }

  // ---- Реестр сносок ----
  function createFootnoteRegistry() {
    const notes = new Map();
    const order = [];
    const index = new Map();

    function define(noteId, text) {
      notes.set(noteId, text);
    }

    function ref(noteId) {
      if (!index.has(noteId)) {
        index.set(noteId, order.length + 1);
        order.push(noteId);
      }
      const n = index.get(noteId);
      const sup = document.createElement("sup");
      const a = document.createElement("a");
      a.id = `fnref-${noteId}`;
      a.href = `#fn-${noteId}`;
      a.textContent = String(n);
      a.className = "footnote-ref";
      sup.appendChild(a);
      return sup;
    }

    function buildSection() {
      if (!order.length) return null;
      const section = document.createElement("section");
      section.className = "article-footnotes";
      const h = document.createElement("h2");
      h.textContent = "Сноски";
      section.appendChild(h);
      const ol = document.createElement("ol");
      for (let i = 0; i < order.length; i++) {
        const noteId = order[i];
        const li = document.createElement("li");
        li.id = `fn-${noteId}`;
        const p = document.createElement("p");
        appendInlineInto(p, notes.get(noteId) || "", api);
        const back = document.createElement("a");
        back.href = `#fnref-${noteId}`;
        back.className = "footnote-back";
        back.textContent = "↩";
        back.setAttribute("aria-label", "Вернуться к тексту");
        p.appendChild(document.createTextNode(" "));
        p.appendChild(back);
        li.appendChild(p);
        ol.appendChild(li);
      }
      section.appendChild(ol);
      return section;
    }

    const api = { notes, order, index, define, ref, buildSection };
    return api;
  }

  // ---- Inline markdown с рекурсией ----
  function appendInlineInto(target, text, registry) {
    const src = String(text ?? "");
    const re = /\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|`([^`]+)`|\[([^\]]+)\]\s*\(([^)\s]+)\)|\[\^([^\]]+)\]/g;
    let offset = 0;
    let m;
    while ((m = re.exec(src)) !== null) {
      target.appendChild(document.createTextNode(src.slice(offset, m.index)));
      if (m[1] !== undefined) {
        const strong = document.createElement("strong");
        appendInlineInto(strong, m[1], registry);
        target.appendChild(strong);
      } else if (m[2] !== undefined) {
        const em = document.createElement("em");
        appendInlineInto(em, m[2], registry);
        target.appendChild(em);
      } else if (m[3] !== undefined) {
        const code = document.createElement("code");
        code.textContent = m[3];
        target.appendChild(code);
      } else if (m[4] !== undefined) {
        if (/^(https?:\/\/|mailto:|\/(?![\/\\])|\.\.?\/|#|\?)/i.test(m[5]) && !/[\\\u0000-\u0020]/.test(m[5])) {
          const link = document.createElement("a");
          link.textContent = m[4];
          link.href = m[5];
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          target.appendChild(link);
        } else {
          target.appendChild(document.createTextNode(m[0]));
        }
      } else if (m[6] !== undefined) {
        target.appendChild(registry.ref(m[6]));
      }
      offset = m.index + m[0].length;
    }
    target.appendChild(document.createTextNode(src.slice(offset)));
  }

  // ---- Разбор чанка ----
  function renderChunkInto(container, text, registry) {
    const raw = String(text ?? "").replace(/\r\n?/g, "\n");
    const allLines = raw.split("\n");
    const lines = [];
    for (let i = 0; i < allLines.length; i++) {
      const m = /^\s*\[\^([^\]]+)\]:\s*(.+)$/.exec(allLines[i]);
      if (m) registry.define(m[1], m[2].trim());
      else lines.push(allLines[i]);
    }

    let paragraph = [];
    let list = null;

    function flushParagraph() {
      if (paragraph.length) {
        const p = document.createElement("p");
        appendInlineInto(p, paragraph.join("\n"), registry);
        container.appendChild(p);
        paragraph = [];
      }
    }
    function flushList() {
      if (list) { container.appendChild(list); list = null; }
    }

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (!trimmed) { flushParagraph(); flushList(); continue; }

      const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if (heading) {
        flushParagraph(); flushList();
        const tag = heading[1].length <= 2 ? "h2" : "h3";
        const h = document.createElement(tag);
        appendInlineInto(h, heading[2], registry);
        container.appendChild(h);
        continue;
      }

      const bullet = /^([-*]|\d+\.)\s+(.+)$/.exec(trimmed);
      if (bullet) {
        flushParagraph();
        const isOrdered = /^\d/.test(bullet[1]);
        const tag = isOrdered ? "ol" : "ul";
        if (!list || list.tagName.toLowerCase() !== tag) {
          flushList();
          list = document.createElement(tag);
        }
        const li = document.createElement("li");
        appendInlineInto(li, bullet[2], registry);
        list.appendChild(li);
        continue;
      }

      flushList();
      paragraph.push(trimmed);
    }
    flushParagraph(); flushList();

    if (!container.firstChild && String(text).trim()) {
      const p = document.createElement("p");
      appendInlineInto(p, text, registry);
      container.appendChild(p);
    }
  }

  // ---- Рендер тела статьи с единым реестром ----
  function renderBody(chunks) {
    const registry = createFootnoteRegistry();
    const fragment = document.createDocumentFragment();
    const blocks = [];
    for (let i = 0; i < chunks.length; i++) {
      const section = document.createElement("section");
      section.className = "article-chunk";
      renderChunkInto(section, chunks[i], registry);
      blocks.push(section);
    }
    for (let i = 0; i < blocks.length; i++) fragment.appendChild(blocks[i]);
    const notes = registry.buildSection();
    if (notes) fragment.appendChild(notes);
    return fragment;
  }

  function renderInlineInto(el, text) {
    if (!el) return;
    clear(el);
    const registry = createFootnoteRegistry();
    appendInlineInto(el, text ?? "", registry);
  }

  // ---- Избранное ----
  async function refreshFavoriteStatus() {
    if (!favBtn || resolvedId == null) return;
    try {
      await window.ZPAuth.ready;
      if (!window.ZPAuth.isLoggedIn()) {
        favBtn.disabled = true;
        favBtn.title = "Войдите, чтобы добавить в избранное";
        removeClass(favBtn, "is-active");
        favBtn.setAttribute("aria-pressed", "false");
        return;
      }
      favBtn.disabled = false;
      const raw = await request("cabinet/favorites?limit=100");
      const favorites = Array.isArray(raw) ? raw : (raw?.items || []);
      const isFav = favorites.some((f) => f && String(f.content_item_id) === String(resolvedId));
      applyFavoriteState(isFav);
    } catch (e) {
      if (favBtn) favBtn.disabled = false;
    }
  }

  function applyFavoriteState(isFav) {
    if (!favBtn) return;
    if (isFav) addClass(favBtn, "is-active"); else removeClass(favBtn, "is-active");
    favBtn.setAttribute("aria-pressed", String(isFav));
    favBtn.title = isFav ? "Удалить из избранного" : "Добавить в избранное";
  }

  if (favBtn) {
    favBtn.addEventListener("click", async () => {
      if (!window.ZPAuth.isLoggedIn()) {
        window.location.href = "./login.html";
        return;
      }
      if (resolvedId == null) return;
      if (favBtn.dataset && favBtn.dataset.busy === "1") return;
      if (favBtn.dataset) favBtn.dataset.busy = "1";
      favBtn.disabled = true;

      const isActive = hasClass(favBtn, "is-active");
      try {
        if (isActive) {
          await request(`cabinet/favorites/${resolvedId}`, { method: "DELETE" });
          applyFavoriteState(false);
        } else {
          await request(`cabinet/favorites/${resolvedId}`, { method: "POST" });
          applyFavoriteState(true);
        }
      } catch (error) {
        if (error.status === 409 && !isActive) applyFavoriteState(true);
        else {
          const statusEl = $("#status");
          if (statusEl) statusEl.textContent = "Ошибка: " + error.message;
        }
      } finally {
        if (favBtn.dataset) favBtn.dataset.busy = "";
        favBtn.disabled = false;
      }
    });
  }

  // ---- Рендер статьи ----
  function render(record) {
    if (!record || typeof record !== "object") {
      throw Object.assign(new Error("Статья не найдена"), { status: 404 });
    }

    resolvedId = record.id != null ? String(record.id) : null;

    document.title = `${record.title || "Статья"} — Законпозитор`;

    renderInlineInto($("#article-title"), record.title || "");

    const category = record.category && typeof record.category === "object" ? record.category : null;
    const categoryName = (category && category.name) || "Полезные материалы";
    setText($("#article-category"), categoryName);

    const catPath = $("#article-category-path");
    if (catPath) {
      if (category) {
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
      if (summaryText) {
        renderInlineInto(summaryEl, summaryText);
        summaryEl.hidden = false;
      } else {
        clear(summaryEl);
        summaryEl.hidden = true;
      }
    }

    // Чанки
    const rawChunks = record.chunks ?? record.body ?? record.content;
    const chunks = Array.isArray(rawChunks)
      ? rawChunks.map((c) => String(c ?? ""))
      : typeof rawChunks === "string"
        ? [rawChunks]
        : [];

    // Время чтения
    const words = chunks.join(" ").match(/\S+/g)?.length || 0;
    const minutes = Math.max(1, Math.ceil(words / 200));
    setText($("#article-reading-time"), `${minutes} мин. чтения`);

    // Дата публикации/проверки
    const datesEl = $("#article-dates");
    if (datesEl) {
      const fmt = (value) => {
        if (!value) return "";
        const d = new Date(value);
        return Number.isNaN(d.getTime())
          ? ""
          : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
      };
      const published = fmt(record.published_at);
      const checked = fmt(record.checked_at || record.reviewed_at || record.updated_at);
      const parts = [];
      if (published) parts.push(`Дата публикации/проверки: ${published}`);
      if (checked && checked !== published) parts.push(`Проверено: ${checked}`);
      if (parts.length) {
        datesEl.textContent = parts.join(" · ");
        datesEl.hidden = false;
      } else {
        datesEl.hidden = true;
      }
    }

    const introEl = $("#article-intro");
    const introBody = $("#article-intro-body");
    const chunksEl = $("#article-chunks");
    const emptyEl = $("#article-empty");

    if (introBody) clear(introBody);
    if (chunksEl) clear(chunksEl);

    if (!chunks.length) {
      if (introEl) introEl.hidden = true;
      if (emptyEl) emptyEl.hidden = false;
    } else {
      if (introEl) introEl.hidden = !summaryText;
      if (emptyEl) emptyEl.hidden = true;

      const registry = createFootnoteRegistry();

      if (introBody) {
        const introSection = document.createElement("div");
        renderChunkInto(introSection, chunks[0], registry);
        while (introSection.firstChild) introBody.appendChild(introSection.firstChild);
      }
      for (let i = 1; i < chunks.length; i++) {
        const section = document.createElement("section");
        section.className = "article-chunk";
        renderChunkInto(section, chunks[i], registry);
        if (chunksEl) chunksEl.appendChild(section);
      }
      const notes = registry.buildSection();
      if (notes) {
        if (chunksEl) chunksEl.appendChild(notes);
        else if (introBody) introBody.appendChild(notes);
      }
    }

    hide(state);
    show(article);

    refreshFavoriteStatus();
  }

  // ---- Рекомендации ----
  async function loadRelated() {
    const list = $("#related-articles-list");
    const card = $("#related-articles");
    if (!list || !card) return;
    try {
      const raw = await request("public/articles?limit=4");
      const records = Array.isArray(raw) ? raw : (raw?.items || []);
      clear(list);
      const filtered = [];
      for (let i = 0; i < records.length && filtered.length < 3; i++) {
        const rec = records[i];
        // Исключаем текущую статью по id (у записей в public/articles есть id)
        if (resolvedId != null && String(rec.id) === String(resolvedId)) continue;
        filtered.push(rec);
      }
      if (!filtered.length) { card.hidden = true; return; }
      for (let i = 0; i < filtered.length; i++) {
        const rec = filtered[i];
        const href = articleHref(rec);
        if (!href) continue;
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = href;
        renderInlineInto(a, rec.title || "Без названия");
        li.appendChild(a);
        list.appendChild(li);
      }
      card.hidden = !list.children.length;
    } catch {
      card.hidden = true;
    }
  }

  // ---- Загрузка ----
  async function load() {
    show(state);
    if (state) state.setAttribute("aria-busy", "true");
    hide(article);
    const retryBtn = $("#retry-article");
    hide(retryBtn);
    resolvedId = null;

    setText($("#state-title"), "Загружаем статью…");
    setText($("#state-message"), "Получаем материал");

    try {
      const path = slug
        ? `public/articles/${encodeURIComponent(slug)}`
        : `public/articles/${encodeURIComponent(id)}`;
      const record = await request(path);
      if (!record || typeof record !== "object") {
        throw Object.assign(new Error("Статья не найдена"), { status: 404 });
      }
      render(record);
      loadRelated();
    } catch (error) {
      setText($("#state-title"), error.status === 404
        ? "Статья не найдена" : "Не удалось загрузить статью");
      setText($("#state-message"), error.status === 404
        ? "Возможно, материал ещё не опубликован или был удалён. Доступны другие статьи."
        : error.message);
      if (error.status !== 404) show(retryBtn);
    } finally {
      if (state) state.setAttribute("aria-busy", "false");
    }
  }

  const retryEl = $("#retry-article");
  if (retryEl) retryEl.addEventListener("click", load);
  if (slug) {
    load();
    return;
  }
  if (!id || !/^[1-9]\d*$/.test(id) || BigInt(id) > 9223372036854775807n) {
    show(state);
    if (state) state.setAttribute("aria-busy", "false");
    setText($("#state-title"), "Статья не выбрана");
    setText($("#state-message"), "Откройте статью из результатов поиска.");
    hide(article);
    return;
  }

  load();
});