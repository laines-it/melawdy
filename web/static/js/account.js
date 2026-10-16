document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  let version = 0;

  function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  async function update(session) {
    const currentVersion = ++version;
    for (const kind of ["documents", "articles", "surveys"]) {
      document.querySelector(`#stat-${kind}`).textContent = "—";
    }
    const documents = document.querySelector("#account-documents");
    const calculations = document.querySelector("#account-calculations");
    documents.replaceChildren();
    calculations.replaceChildren();
    if (!session) return;
    const user = session.user;
    document.querySelector("#profile-name").textContent = user.full_name;
    document.querySelector("#profile-email").textContent = user.email;
    const roles = { admin: "Администратор", individual: "Физическое лицо", organization: "Организация", lawyer: "Юрист" };
    document.querySelector("#profile-role").textContent = roles[user.user_type] || user.user_type;
    document.querySelector(".profile-avatar").textContent = user.full_name.split(/\s+/)
      .slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    try {
      const result = await request("account/overview");
      if (currentVersion !== version) return;
      for (const [kind, count] of Object.entries(result.stats)) {
        document.querySelector(`#stat-${kind}`).textContent = count;
      }
      if (!result.documents.length) documents.append(element("p", "У вас пока нет документов."));
      for (const record of result.documents) {
        const card = element("article", "");
        card.append(element("h3", record.title), element("p", `Статус: ${record.status}`));
        if (record.due_date) card.append(element("p", `Срок: ${record.due_date}`));
        documents.append(card);
      }
      if (!result.calculations.length) calculations.append(element("p", "Сохранённых расчётов пока нет."));
      for (const record of result.calculations) {
        calculations.append(element("p", `Расчёт №${record.id}: ${record.total_amount} ${record.currency}`));
      }
    } catch (error) {
      if (currentVersion === version) document.querySelector("#status").textContent = error.message;
    }
  }

  document.addEventListener("auth-change", (event) => update(event.detail));
});
