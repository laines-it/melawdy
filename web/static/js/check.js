document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const status = document.querySelector("#upload-status");
  const list = document.querySelector("#templates-list");
  const preview = document.querySelector("#template-preview");
  const more = document.querySelector("#more-templates");
  let offset = 0;
  const pageSize = 25;

  function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  request("public/capabilities").then((capabilities) => {
    status.textContent = capabilities.music_check.message;
  }).catch((error) => { status.textContent = error.message; });

  async function loadTemplates() {
    more.disabled = true;
    try {
      const templates = await request(`public/templates?limit=${pageSize}&offset=${offset}`);
      if (!templates.length && offset === 0) list.textContent = "Шаблоны пока не опубликованы.";
      for (const template of templates) {
        const card = element("div", "");
        card.className = "template-card";
        card.style.setProperty("--template-bg", "#F2E0FC");
        const title = element("h3", template.title);
        title.className = "template-title";
        const description = element("p", template.description || "");
        description.className = "template-desc";
        card.append(title, description);
        const button = element("button", "Открыть шаблон →");
        button.type = "button";
        button.className = "template-download";
        button.addEventListener("click", async () => {
          button.disabled = true;
          try {
            const record = await request(`public/templates/${encodeURIComponent(template.id)}`);
            preview.replaceChildren(element("h3", record.title), element("pre", record.body));
            preview.hidden = false;
          } catch (error) {
            document.querySelector("#templates-status").textContent = error.message;
          } finally {
            button.disabled = false;
          }
        });
        card.append(button);
        list.append(card);
      }
      offset += templates.length;
      more.hidden = templates.length < pageSize;
      document.querySelector("#templates-status").textContent = "";
    } catch (error) {
      document.querySelector("#templates-status").textContent = error.message;
    } finally {
      more.disabled = false;
    }
  }

  more.addEventListener("click", loadTemplates);
  loadTemplates();
});
