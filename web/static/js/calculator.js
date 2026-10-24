document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const form = document.querySelector("#fee-calculator-form");
  const options = document.querySelector("#fee-options");
  const status = document.querySelector("#status");
  const save = document.querySelector("#save-calculation");
  const total = document.querySelector("#fee-total");
  const details = document.querySelector("#fee-details");
  const state = {};
  let catalog, result, payload, ready = false, saving = false, version = 0;
  let choices = [];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function field(id, title, control) {
    const wrapper = element("div", "", "fee-field");
    const label = element("label", title);
    label.htmlFor = control.id = `fee-${id}`;
    wrapper.append(label, control);
    options.append(wrapper);
    return wrapper;
  }

  function choice(id, title, items, key = "id", label = "name") {
    choices.push(id);
    const select = document.createElement("select");
    select.required = true;
    select.append(new Option("Выберите вариант", ""));
    items.forEach((item) => select.append(new Option(item[label], item[key])));
    select.value = state[id] || "";
    const selected = items.find((item) => item[key] === select.value);
    const wrapper = field(id, title, select);
    if (selected?.description) wrapper.append(element("small", selected.description));
    select.addEventListener("change", () => {
      for (const key of choices.slice(choices.indexOf(id) + 1)) delete state[key];
      state[id] = select.value;
      if (id === "procedure") {
        delete state.stages;
        state.need_paper_certificate = false;
      }
      render();
    });
    return selected;
  }

  function number(id, title, minimum = 1, initial = 1) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = minimum;
    input.step = id === "claim_amount" ? "0.01" : "1";
    input.required = true;
    input.value = state[id] ?? initial;
    state[id] = input.value;
    input.addEventListener("input", () => {
      state[id] = input.value;
      calculate();
    });
    field(id, title, input);
  }

  function registration(procedure) {
    const stages = procedure.stage_selection;
    state.stages ??= [...stages.default_selected];
    const group = element("fieldset", "", "fee-stages");
    group.append(element("legend", stages.title));
    for (const stage of stages.stages) {
      const label = element("label", "", "fee-stage");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = state.stages.includes(stage.id);
      input.addEventListener("change", () => {
        state.stages = input.checked ? [...state.stages, stage.id]
          : state.stages.filter((id) => id !== stage.id);
        state.need_paper_certificate = state.stages.includes("paper_certificate");
        render();
      });
      label.append(input, element("span", stage.name));
      group.append(label);
    }
    options.append(group);
    if (!state.stages.length) return false;
    for (const item of procedure.application_parameters.fields) {
      if (item.type === "integer") {
        number(item.id, item.name, item.minimum, item.default);
      } else if (item.type === "boolean") {
        const select = document.createElement("select");
        select.append(new Option("Нет", "false"), new Option("Да", "true"));
        select.value = String(state.stages.includes("paper_certificate"));
        select.addEventListener("change", () => {
          state.need_paper_certificate = select.value === "true";
          state.stages = state.stages.filter((id) => id !== "paper_certificate");
          if (state.need_paper_certificate) state.stages.push("paper_certificate");
          render();
        });
        field(item.id, item.name, select);
      }
    }
    return true;
  }

  function litigation(procedure) {
    const action = choice("action", "Вид обращения", [
      { id: "claim", name: procedure.claim_type.title },
      { id: "rospatent_appeal", name: procedure.rospatent_appeal.name },
      { id: "appeals", name: procedure.appeals.name },
    ]);
    if (!action) return false;
    let branch = procedure[action.id];
    if (action.id !== "rospatent_appeal") {
      const court = choice("court_id", action.id === "appeals" ? branch.question
        : procedure.court_selection.title, procedure.court_selection.options);
      if (!court) return false;
      if (action.id === "appeals") {
        branch = branch.courts.find((item) => item.court === court.name);
        branch = choice("complaint", branch.question, branch.complaints, "name");
        if (!branch) return false;
      } else {
        const claim = choice("claim_type", procedure.claim_type.title, procedure.claim_type.options);
        if (!claim) return false;
        if (claim.id === "property") {
          number("claim_amount", "Сумма иска, ₽", 0, 0);
          return true;
        }
        branch = claim.courts.find((item) => item.court === court.name);
      }
    }
    return Boolean(choice("applicant", branch.question || "Кто подаёт?", branch.options, "applicant", "applicant"));
  }

  function render() {
    options.replaceChildren();
    choices = [];
    const procedure = choice("procedure", catalog.title, [
      ...catalog.procedures, { id: "service_selection", name: catalog.service_selection.name },
    ]);
    ready = false;
    if (procedure?.id === "service_selection") {
      ready = Boolean(choice("service", catalog.service_selection.name, catalog.service_selection.options));
    } else if (procedure?.stage_selection) {
      ready = registration(procedure);
    } else if (procedure?.court_selection) {
      ready = litigation(procedure);
    }
    calculate();
  }

  function parameters() {
    return {
      procedure_id: state.procedure === "service_selection" ? state.service : state.procedure,
      ...(state.procedure === "trademark_registration" ? {
        stages: state.stages, classes: Number(state.classes),
        item_names_per_class: Number(state.item_names_per_class),
        need_paper_certificate: state.need_paper_certificate,
      } : {}),
      ...(state.procedure === "court_disputes" ? {
        court_id: state.court_id, claim_type: state.action === "claim" ? state.claim_type : state.action,
        claim_amount: state.claim_amount || "0", complaint: state.complaint, applicant: state.applicant,
      } : {}),
    };
  }

  function money(amount) {
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency: result.currency }).format(amount);
  }

  function range(low, high) {
    return Number(low) === Number(high) ? money(low) : `${money(low)} – ${money(high)}`;
  }

  function show(value) {
    result = value;
    total.textContent = `${value.approximate ? "≈ " : ""}${range(value.total_amount, value.total_max_amount)}`;
    details.replaceChildren();
    for (const item of value.breakdown) {
      details.append(element("p", `${item.name}: ${range(item.amount, item.max_amount)}`));
      if (item.formula) details.append(element("p", item.formula));
      if (item.note) details.append(element("p", item.note));
    }
    save.disabled = saving;
  }

  async function calculate() {
    const current = ++version;
    result = payload = null;
    save.disabled = true;
    total.textContent = "—";
    details.replaceChildren();
    if (!ready || !form.checkValidity()) {
      status.textContent = ready ? "Заполните параметры расчёта." : "Выберите следующие параметры процедуры.";
      return;
    }
    const body = parameters();
    status.textContent = "Выполняется расчёт…";
    try {
      const value = await request("public/fees/tree/calculate", { method: "POST", body: JSON.stringify(body) });
      if (current !== version) return;
      payload = body;
      show(value);
      status.textContent = "";
    } catch (error) {
      if (current === version) status.textContent = error.message;
    }
  }

  form.addEventListener("submit", (event) => event.preventDefault());
  save.addEventListener("click", async () => {
    if (!result || saving) return;
    const current = version;
    try {
      await window.ZPAuth.ready.catch(() => {});
      if (!window.ZPAuth.isLoggedIn()) {
        status.textContent = "Войдите в аккаунт, чтобы сохранить расчёт.";
        return;
      }
      if (current !== version || !result || saving) return;
      saving = true;
      save.disabled = true;
      const saved = await request("public/fees/tree/calculations", { method: "POST", body: JSON.stringify(payload) });
      if (current !== version) return;
      show(saved);
      status.textContent = `Расчёт №${saved.id} сохранён в личном кабинете.`;
    } catch (error) {
      if (current === version) status.textContent = error.message;
    } finally {
      saving = false;
      save.disabled = !result;
    }
  });

  request("public/fees/tree").then((value) => {
    catalog = value;
    render();
  }).catch((error) => { status.textContent = error.message; });
});
