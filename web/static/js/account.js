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
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
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
    document.querySelector("#profile-name").textContent = user.full_name;
    document.querySelector("#profile-email").textContent = user.email;
    document.querySelector("#profile-role").textContent = roleLabels[user.user_type] || user.user_type;
    document.querySelector(".profile-avatar").textContent = user.full_name.split(/\s+/)
      .slice(0, 2).map((part) => part[0]).join("").toUpperCase();
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
      const card = element("article", "");
      card.className = "case-card";

      const head = element("div", "");
      head.className = "case-card-head";
      head.append(
        element("h3", doc.title),
        element("span", statusLabels[doc.status] || doc.status),
      );
      head.children[0].className = "case-card-title";
      head.children[1].className = `case-status status-${doc.status}`;

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
      open.href = "#"; // TODO: ссылка на конструктор, когда появится
      open.addEventListener("click", (event) => {
        event.preventDefault();
        document.querySelector("#status").textContent = "Просмотр документа пока недоступен.";
      });

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

  // ---- Рендер избранных статей ----
  function renderFavorites(favorites) {
    const container = document.querySelector("#account-favorites");
    container.replaceChildren();
    if (!favorites.length) {
      container.append(element("p", "У вас пока нет избранных статей."));
      return;
    }
    for (const fav of favorites) {
      const card = element("article", "");
      card.className = "case-card";

      const title = element("h3", fav.title);
      title.className = "case-card-title";

      const meta = element("p", `Добавлено: ${formatDate(fav.created_at)}`);
      meta.className = "case-card-meta";

      const summary = element("p", fav.summary || "Краткое описание отсутствует.");
      summary.className = "case-card-text";

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

  // ---- Рендер расчётов (как было) ----
  function renderCalculations(calculations) {
    const container = document.querySelector("#account-calculations");
    container.replaceChildren();
    if (!calculations.length) {
      container.append(element("p", "Сохранённых расчётов пока нет."));
      return;
    }
    for (const record of calculations) {
      container.append(element("p", `Расчёт №${record.id}: ${record.total_amount} ${record.currency}`));
    }
  }

  // ---- Основная загрузка ----
  async function update(session) {
    const currentVersion = ++version;
    for (const kind of ["documents", "articles", "surveys"]) {
      document.querySelector(`#stat-${kind}`).textContent = "—";
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
      const [overview, documents, favorites] = await Promise.all([
        request("account/overview"),
        request("cabinet/documents?limit=25"),
        request("cabinet/favorites?limit=25"),
      ]);
      if (currentVersion !== version) return;

      // Статистика в профиле
      document.querySelector("#stat-documents").textContent = overview.stats.documents ?? 0;
      document.querySelector("#stat-articles").textContent = overview.stats.articles ?? 0;
      document.querySelector("#stat-surveys").textContent = overview.stats.surveys ?? 0;

      // Списки
      renderDocuments(documents);
      renderFavorites(favorites);
      renderCalculations(overview.calculations || []);
    } catch (error) {
      if (currentVersion !== version) return;
      document.querySelector("#status").textContent = error.message;
      documentsBox.replaceChildren(element("p", "Не удалось загрузить документы."));
      favoritesBox.replaceChildren(element("p", "Не удалось загрузить статьи."));
    }
  }

  document.addEventListener("auth-change", (event) => update(event.detail));
});