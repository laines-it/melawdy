document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const form = document.querySelector("#fee-calculator-form");
  const applicationSelect = document.querySelector("#application-type");
  const classSelect = document.querySelector("#mkty-class");
  const urgentSelect = document.querySelector("#is-urgent");
  const saveButton = document.querySelector("#save-calculation");
  const status = document.querySelector("#status");
  let catalog = null;
  let result = null;
  let version = 0;
  let saving = false;

  function option(value, text) {
    const element = document.createElement("option");
    element.value = value;
    element.textContent = text;
    return element;
  }

  function parameters() {
    return {
      application_type_id: Number(applicationSelect.value),
      mktu_class_id: classSelect.value ? Number(classSelect.value) : null,
      is_urgent: urgentSelect.value === "true",
      quantity: Number(document.querySelector("#quantity").value),
    };
  }

  function clearResult() {
    result = null;
    saveButton.disabled = true;
    document.querySelector("#fee-total").textContent = "—";
    document.querySelector("#fee-base").textContent = "—";
    document.querySelector("#fee-quantity").textContent = "—";
    document.querySelector("#fee-legal-basis").textContent = "";
  }

  function render(value) {
    result = value;
    function money(amount) {
      return new Intl.NumberFormat("ru-RU", { style: "currency", currency: value.currency }).format(amount);
    }
    document.querySelector("#fee-total").textContent = money(value.total_amount);
    document.querySelector("#fee-base").textContent = money(value.unit_amount);
    document.querySelector("#fee-quantity").textContent = value.quantity;
    document.querySelector("#fee-legal-basis").textContent = value.legal_basis;
    saveButton.disabled = saving;
  }

  function updateClasses() {
    const previous = classSelect.value;
    const rates = catalog.rates.filter((rate) => rate.application_type_id === applicationSelect.value
      && String(rate.is_urgent) === urgentSelect.value);
    const ids = new Set(rates.map((rate) => rate.mktu_class_id));
    classSelect.replaceChildren();
    if (ids.has(null)) classSelect.append(option("", "Без привязки к классу"));
    for (const item of catalog.mktu_classes.filter((item) => ids.has(item.id))) {
      classSelect.append(option(item.id, `${item.class_number}. ${item.title}`));
    }
    if ([...classSelect.options].some((item) => item.value === previous)) classSelect.value = previous;
    classSelect.disabled = !classSelect.options.length;
  }

  async function calculate() {
    const currentVersion = ++version;
    clearResult();
    if (!catalog) return;
    const selectedClass = catalog.mktu_classes.find((item) => item.id === classSelect.value);
    document.querySelector("#mkty-hint").textContent = selectedClass?.description || "";
    if (!applicationSelect.value || !classSelect.options.length) {
      status.textContent = "Действующие ставки для выбранных параметров пока не настроены.";
      return;
    }
    if (!form.checkValidity()) {
      status.textContent = "Укажите количество от 1 до 100.";
      return;
    }
    status.textContent = "Выполняется расчёт…";
    try {
      const value = await request("public/fees/calculate", { method: "POST", body: JSON.stringify(parameters()) });
      if (currentVersion !== version) return;
      render(value);
      status.textContent = "";
    } catch (error) {
      if (currentVersion === version) status.textContent = error.message;
    }
  }

  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("input", (event) => {
    if ([applicationSelect, urgentSelect].includes(event.target)) updateClasses();
    calculate();
  });
  saveButton.addEventListener("click", async () => {
    if (!result || saving) return;
    const currentVersion = version;
    try {
      await window.ZPAuth.ready.catch(() => {});
      if (!window.ZPAuth.isLoggedIn()) {
        status.textContent = "Войдите в аккаунт, чтобы сохранить расчёт.";
        return;
      }
      if (currentVersion !== version || !result || saving) return;
      saving = true;
      saveButton.disabled = true;
      const saved = await request("public/fees/calculations", { method: "POST", body: JSON.stringify(parameters()) });
      if (currentVersion !== version) return;
      render(saved);
      status.textContent = `Расчёт №${saved.id} сохранён в личном кабинете.`;
    } catch (error) {
      if (currentVersion === version) status.textContent = error.message;
    } finally {
      saving = false;
      saveButton.disabled = !result;
    }
  });

  clearResult();
  request("public/fees/catalog").then((value) => {
    catalog = value;
    const available = new Set(value.rates.map((rate) => rate.application_type_id));
    applicationSelect.replaceChildren(...value.application_types.filter((item) => available.has(item.id))
      .map((item) => option(item.id, item.name)));
    applicationSelect.disabled = !applicationSelect.options.length;
    urgentSelect.disabled = false;
    updateClasses();
    calculate();
  }).catch((error) => { status.textContent = error.message; });
});
