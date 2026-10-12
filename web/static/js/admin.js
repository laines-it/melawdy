document.addEventListener("DOMContentLoaded", () => {
  const $ = (selector) => document.querySelector(selector);
  let csrfToken = "";
  let resources = [];
  let current = null;
  let editingId = null;
  let offset = 0;
  let formVersion = 0;
  const pageSize = 25;
  const controls = new Map();

  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function status(text) { $("#status").textContent = text; }
  function showLogin() {
    csrfToken = "";
    $("#login-section").hidden = false;
    $("#workspace").hidden = true;
  }
  async function api(path, options = {}) {
    const headers = { ...options.headers };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(`/api/v1/${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) {
      if (response.status === 401) showLogin();
      const data = await response.json().catch(() => ({}));
      const detail = Array.isArray(data.detail) ? data.detail.map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ") : data.detail;
      throw new Error(detail || `Ошибка сервера: ${response.status}`);
    }
    return response.status === 204 ? null : response.json();
  }
  function handle(error) { status(error.message); }
  function sectionPath() { return `admin/${encodeURIComponent(current.key)}`; }

  async function buildForm(record = null) {
    const version = ++formVersion;
    const selected = current;
    const foreignKeys = [...new Set(selected.fields.filter((field) => field.kind === "foreign").map((field) => field.resource))];
    const lookups = new Map(await Promise.all(foreignKeys.map(async (key) => [key, await api(`admin/lookups/${key}`)])));
    if (version !== formVersion || selected !== current) return;
    controls.clear();
    $("#fields").replaceChildren();
    editingId = record?.id ?? null;
    $("#form-title").textContent = editingId ? `Редактирование записи ${editingId}` : "Новая запись";
    for (const field of selected.fields) {
      const value = record ? record[field.name] : field.default;
      const wrapper = element("p");
      const label = element("label", field.label + (field.required ? " *" : ""));
      const id = `field-${field.name}`;
      label.htmlFor = id;
      wrapper.append(label, element("br"));
      let input;
      if (field.kind === "texts") {
        const block = element("fieldset");
        block.id = id;
        const list = element("div");
        function addBody(body = "") {
          const row = element("div");
          const area = element("textarea");
          area.rows = 8;
          area.cols = 80;
          area.required = true;
          area.value = body;
          area.setAttribute("aria-label", "Текст раздела статьи");
          const remove = element("button", "Удалить раздел");
          remove.type = "button";
          remove.addEventListener("click", () => row.remove());
          row.append(area, remove, element("br"));
          list.append(row);
        }
        for (const body of value?.length ? value : [""]) addBody(body);
        const add = element("button", "Добавить текстовый раздел");
        add.type = "button";
        add.addEventListener("click", () => addBody());
        block.append(list, add);
        wrapper.append(block);
        controls.set(field.name, { field, read: () => [...list.querySelectorAll("textarea")].map((area) => area.value) });
        $("#fields").append(wrapper);
        continue;
      }
      if (field.kind === "foreign" || field.kind === "enum") {
        input = element("select");
        if (field.nullable || field.kind === "foreign") {
          const empty = element("option", "— Выберите —");
          empty.value = "";
          input.append(empty);
        }
        const options = field.kind === "foreign" ? lookups.get(field.resource) : field.choices.map((choice) => ({ id: choice, label: choice }));
        for (const option of options) {
          const node = element("option", field.kind === "foreign" ? `${option.id}: ${option.label}` : option.label);
          node.value = option.id;
          input.append(node);
        }
        if (value !== null && value !== undefined && ![...input.options].some((option) => option.value === String(value))) {
          const missing = element("option", `ID ${value}`);
          missing.value = String(value);
          input.append(missing);
        }
      } else if (field.kind === "textarea" || field.kind === "json") {
        input = element("textarea");
        input.rows = field.kind === "json" ? 6 : 8;
        input.cols = 80;
      } else {
        input = element("input");
        input.type = field.kind === "boolean" ? "checkbox" : field.kind === "decimal" ? "text" : field.kind;
        if (field.kind === "decimal") input.inputMode = "decimal";
        if (field.kind === "number") input.step = "1";
      }
      input.id = id;
      input.name = field.name;
      input.required = field.required && field.kind !== "boolean";
      if (field.max_length) input.maxLength = field.max_length;
      if (field.minimum !== null && field.minimum !== undefined) input.min = field.minimum;
      if (field.maximum !== null && field.maximum !== undefined) input.max = field.maximum;
      if (field.kind === "boolean") input.checked = Boolean(value);
      else if (field.kind === "json") input.value = JSON.stringify(value ?? {}, null, 2);
      else if (field.kind === "datetime-local" && value) {
        const date = new Date(value);
        input.value = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      } else if (value !== null && value !== undefined) input.value = value;
      wrapper.append(input);
      if (field.kind === "foreign") wrapper.append(element("small", " Сначала создайте связанную запись в соответствующем разделе. В списке — последние 500 записей."));
      controls.set(field.name, { field, input });
      $("#fields").append(wrapper);
    }
  }

  function readForm() {
    const payload = {};
    for (const [name, control] of controls) {
      const { field, input } = control;
      let value = control.read ? control.read() : field.kind === "boolean" ? input.checked : input.value;
      if (field.kind === "texts" && !value.length) throw new Error("Добавьте хотя бы один текстовый раздел статьи.");
      if (value === "" && field.nullable) value = null;
      else if (field.kind === "json") {
        try { value = JSON.parse(value); } catch { throw new Error(`${field.label}: некорректный JSON`); }
      } else if (field.kind === "number" || field.kind === "foreign") {
        if (value === "") throw new Error(`${field.label}: выберите значение`);
        value = Number(value);
        if (!Number.isSafeInteger(value)) throw new Error(`${field.label}: укажите целое число`);
      } else if (field.kind === "datetime-local" && value) value = new Date(value).toISOString();
      payload[name] = value;
    }
    return payload;
  }

  async function loadRecords() {
    const selected = current;
    const result = await api(`${sectionPath()}?limit=${pageSize}&offset=${offset}`);
    if (selected !== current) return;
    $("#records").replaceChildren();
    for (const record of result.items) {
      const row = element("tr");
      const label = record.title ?? record.name ?? record.term ?? record.question ?? record.text ?? record.legal_basis ?? record.code ?? record.survey_id ?? record.content_item_id ?? record.id;
      row.append(element("td", record.id), element("td", String(label).slice(0, 140)));
      const actions = element("td");
      const edit = element("button", "Изменить");
      edit.type = "button";
      edit.addEventListener("click", () => api(`${sectionPath()}/${encodeURIComponent(record.id)}`).then(buildForm).catch(handle));
      const remove = element("button", "Удалить");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Удалить запись ${record.id}?`)) return;
        try {
          await api(`${sectionPath()}/${encodeURIComponent(record.id)}`, { method: "DELETE" });
          if (editingId === record.id) await buildForm();
          if (result.items.length === 1 && offset > 0) offset = Math.max(0, offset - pageSize);
          await loadRecords();
          status("Запись удалена.");
        } catch (error) { handle(error); }
      });
      actions.append(edit, document.createTextNode(" "), remove);
      row.append(actions);
      $("#records").append(row);
    }
    if (!result.items.length) {
      const row = element("tr");
      const cell = element("td", "Пока нет записей.");
      cell.colSpan = 3;
      row.append(cell);
      $("#records").append(row);
    }
    $("#page-status").textContent = result.total ? `${offset + 1}–${offset + result.items.length} из ${result.total}` : "0 записей";
    $("#previous-page").disabled = offset === 0;
    $("#next-page").disabled = offset + pageSize >= result.total;
  }

  async function selectResource() {
    current = resources.find((resource) => resource.key === $("#resource-select").value);
    offset = 0;
    status("");
    $("#resource-title").textContent = current.title;
    await Promise.all([buildForm(), loadRecords()]);
  }
  async function enter(session) {
    csrfToken = session.csrf_token;
    $("#current-user").textContent = `${session.user.full_name} (${session.user.email})`;
    resources = await api("admin/resources");
    $("#resource-select").replaceChildren();
    for (const resource of resources) {
      const option = element("option", resource.title);
      option.value = resource.key;
      $("#resource-select").append(option);
    }
    $("#login-section").hidden = true;
    $("#workspace").hidden = false;
    await selectResource();
  }
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const data = new FormData(event.currentTarget);
      await enter(await api("auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(data)) }));
      $("#login-form").reset();
    } catch (error) { handle(error); }
    finally { button.disabled = false; }
  });
  $("#logout").addEventListener("click", async () => {
    try { await api("auth/logout", { method: "POST" }); showLogin(); status("Вы вышли из аккаунта."); }
    catch (error) { handle(error); }
  });
  $("#resource-select").addEventListener("change", () => selectResource().catch(handle));
  for (const selector of ["#new-record", "#cancel-edit"]) $(selector).addEventListener("click", () => buildForm().catch(handle));
  $("#refresh-list").addEventListener("click", () => loadRecords().catch(handle));
  $("#previous-page").addEventListener("click", () => { offset = Math.max(0, offset - pageSize); loadRecords().catch(handle); });
  $("#next-page").addEventListener("click", () => { offset += pageSize; loadRecords().catch(handle); });
  $("#record-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#save-record");
    button.disabled = true;
    try {
      const payload = readForm();
      await api(sectionPath() + (editingId ? `/${encodeURIComponent(editingId)}` : ""), {
        method: editingId ? "PUT" : "POST", body: JSON.stringify(payload),
      });
      await Promise.all([buildForm(), loadRecords()]);
      status("Запись сохранена.");
    } catch (error) { handle(error); }
    finally { button.disabled = false; }
  });
  api("auth/me").then(enter).catch((error) => {
    showLogin();
    if (!error.message.includes("Войдите")) handle(error);
  });
});
