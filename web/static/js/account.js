document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  let version = 0;

  // ---- Утилиты ----
  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  }

  function asArray(value) {
    if (Array.isArray(value)) return value;
    if (value && Array.isArray(value.items)) return value.items;
    return [];
  }

  // ---- markdown без ссылок и сносок ----
  function stripLinksAndFootnotes(text) {
    let src = String(text ?? "");
    src = src.replace(/\[([^\]]+)\]\s*\([^)\s]*\)/g, "$1");
    src = src.replace(/\[\^[^\]]+\]/g, "");
    return src;
  }

  function renderInlineMarkdownInto(el, text) {
    if (!el) return;
    el.replaceChildren();
    const src = stripLinksAndFootnotes(text);
    const tokens = /\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|`([^`]+)`/g;
    let offset = 0;
    for (const match of src.matchAll(tokens)) {
      el.append(document.createTextNode(src.slice(offset, match.index)));
      if (match[1] !== undefined || match[2] !== undefined) {
        const node = document.createElement(match[1] !== undefined ? "strong" : "em");
        node.textContent = match[1] ?? match[2];
        el.append(node);
      } else if (match[3] !== undefined) {
        const code = document.createElement("code");
        code.textContent = match[3];
        el.append(code);
      }
      offset = match.index + match[0].length;
    }
    el.append(document.createTextNode(src.slice(offset)));
  }

  const statusLabels = {
    draft: "Нужно сделать",
    in_progress: "В процессе",
    completed: "Готово",
    archived: "Архив",
  };

  const roleLabels = {
    admin: "Администратор",
    individual: "Физическое лицо",
    organization: "Организация",
    lawyer: "Юрист",
  };

  // ---- Сворачивание блоков ----
  document.querySelectorAll(".collapse-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const content = document.getElementById(btn.dataset.target);
      if (!content) return;
      const collapsed = content.hidden;
      content.hidden = !collapsed;
      btn.setAttribute("aria-expanded", String(collapsed));
      const icon = btn.querySelector(".collapse-icon");
      if (icon) icon.textContent = collapsed ? "▼" : "▶";
    });
  });

  // ---- Рендер профиля ----
  function renderProfile(user) {
    if (!user) return;
    const name = user.full_name || user.email || "—";
    document.querySelector("#profile-name").textContent = name;
    document.querySelector("#profile-email").textContent = user.email || "—";
    document.querySelector("#profile-role").textContent =
      roleLabels[user.user_type] || user.user_type || "—";
    document.querySelector(".profile-avatar").textContent = name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
  }

  // ---- Рендер документов ----
  function renderDocuments(docs) {
    const container = document.querySelector("#account-documents");
    container.replaceChildren();
    if (!docs.length) {
      container.append(element("p", "У вас пока нет документов."));
      return;
    }
    for (const doc of docs) {
      if (!doc || typeof doc !== "object") continue;
      const card = element("article", "");
      card.className = "case-card";

      const head = element("div", "");
      head.className = "case-card-head";
      head.append(
        element("h3", doc.title || "Без названия"),
        element("span", statusLabels[doc.status] || doc.status || "—"),
      );
      head.children[0].className = "case-card-title";
      head.children[1].className = `case-status status-${doc.status || "draft"}`;

      const meta = element("p", `Создано: ${formatDate(doc.created_at)}`);
      meta.className = "case-card-meta";
      if (doc.due_date) meta.textContent += ` · Срок: ${formatDate(doc.due_date)}`;

      const footer = element("div", "");
      footer.className = "case-card-footer";

      const statusBtn = element("button", "Сменить статус");
      statusBtn.type = "button";
      statusBtn.className = "button-secondary small";
      statusBtn.addEventListener("click", async () => {
        const next = nextStatus(doc.status);
        statusBtn.disabled = true;
        try {
          await request(`cabinet/documents/${doc.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: next }),
          });
          doc.status = next;
          head.children[1].className = `case-status status-${next}`;
          head.children[1].textContent = statusLabels[next] || next;
        } catch (error) {
          document.querySelector("#status").textContent = error.message;
        } finally {
          statusBtn.disabled = false;
        }
      });

      const open = element("a", "Открыть документ →");
      open.className = "case-link";
      open.href = `./documents.html?document=${encodeURIComponent(doc.id)}`;

      footer.append(statusBtn, open);
      card.append(head, meta, footer);
      container.append(card);
    }
  }

  function nextStatus(current) {
    const order = ["draft", "in_progress", "completed"];
    const index = order.indexOf(current);
    return order[(index + 1) % order.length];
  }

  // ---- Рендер избранных статей (markdown без ссылок и сносок) ----
  function renderFavorites(favorites) {
    const container = document.querySelector("#account-favorites");
    container.replaceChildren();
    if (!favorites.length) {
      container.append(element("p", "У вас пока нет избранных статей."));
      return;
    }
    for (const fav of favorites) {
      if (!fav || typeof fav !== "object") continue;
      const card = element("article", "");
      card.className = "case-card";

      const title = element("h3");
      title.className = "case-card-title";
      renderInlineMarkdownInto(title, fav.title || "Без названия");

      const meta = element("p", `Добавлено: ${formatDate(fav.created_at)}`);
      meta.className = "case-card-meta";

      const summary = element("p");
      summary.className = "case-card-text";
      renderInlineMarkdownInto(summary, fav.summary || "Краткое описание отсутствует.");

      const footer = element("div", "");
      footer.className = "case-card-footer";
      const read = element("a", "Читать далее →");
      read.className = "case-link";
      read.href = `./article.html?id=${encodeURIComponent(fav.content_item_id)}`;
      footer.append(read);

      card.append(title, meta, summary, footer);
      container.append(card);
    }
  }

  // ---- Рендер расчётов ----
  function renderCalculations(calculations) {
    const container = document.querySelector("#account-calculations");
    container.replaceChildren();
    const list = asArray(calculations);
    if (!list.length) {
      container.append(element("p", "Сохранённых расчётов пока нет."));
      return;
    }
    for (const record of list) {
      if (!record || typeof record !== "object") continue;
      container.append(
        element("p", `Расчёт №${record.id}: ${record.total_amount} ${record.currency || ""}`.trim())
      );
    }
  }

  // ---- Основная загрузка ----
  async function update(session) {
    const currentVersion = ++version;
    for (const kind of ["documents", "articles", "surveys"]) {
      const stat = document.querySelector(`#stat-${kind}`);
      if (stat) stat.textContent = "—";
    }
    const documentsBox = document.querySelector("#account-documents");
    const favoritesBox = document.querySelector("#account-favorites");
    const calculationsBox = document.querySelector("#account-calculations");
    documentsBox.replaceChildren(element("p", "Загрузка…"));
    favoritesBox.replaceChildren(element("p", "Загрузка…"));
    calculationsBox.replaceChildren();

    if (!session) return;
    renderProfile(session.user);

    try {
      const [overview, documentsRaw, favoritesRaw] = await Promise.all([
        request("account/overview"),
        request("cabinet/documents?limit=25"),
        request("cabinet/favorites?limit=25"),
      ]);
      if (currentVersion !== version) return;

      const stats = overview?.stats || {};
      document.querySelector("#stat-documents").textContent = stats.documents ?? 0;
      document.querySelector("#stat-articles").textContent = stats.articles ?? 0;
      document.querySelector("#stat-surveys").textContent = stats.surveys ?? 0;

      renderDocuments(asArray(documentsRaw));
      renderFavorites(asArray(favoritesRaw));
      renderCalculations(overview?.calculations || []);
    } catch (error) {
      if (currentVersion !== version) return;
      document.querySelector("#status").textContent = error.message;
      documentsBox.replaceChildren(element("p", "Не удалось загрузить документы."));
      favoritesBox.replaceChildren(element("p", "Не удалось загрузить статьи."));
    }
  }

  document.addEventListener("auth-change", (event) => update(event.detail));
});