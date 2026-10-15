document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#fee-calculator-form");
  const mktySelect = document.querySelector("#mkty-class");
  const applicantSelect = document.querySelector("#applicant-type");
  const quantityInput = document.querySelector("#quantity");
  const benefitSelect = document.querySelector("#benefit");
  const feeTotal = document.querySelector("#fee-total");
  const feeBase = document.querySelector("#fee-base");
  const feeExtra = document.querySelector("#fee-extra");
  const mktyHint = document.querySelector("#mkty-hint");
  const saveButton = document.querySelector("#save-calculation");

  // Справочник классов МКТУ (краткое описание)
  const MKTY_DESCRIPTIONS = {
    1: "Класс 1: химические продукты, используемые в промышленности.",
    2: "Класс 2: краски, лаки, защитные покрытия.",
    3: "Класс 3: косметика, парфюмерия, чистящие средства.",
    4: "Класс 4: промышленные масла, смазки, топливо.",
    5: "Класс 5: фармацевтические препараты, медицинские изделия.",
  };

  // Базовые ставки (в рублях) — примерные значения
  const BASE_FEE = {
    individual: 4900,
    legal: 8500,
    ip: 4900,
  };

  // Стоимость за дополнительный класс МКТУ
  const EXTRA_CLASS_FEE = 3400;

  // Коэффициенты льгот
  const BENEFIT_COEFFICIENT = {
    none: 1,
    "small-business": 0.5,
    disabled: 0.3,
    veteran: 0.3,
  };

  function formatMoney(value) {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: "RUB",
      maximumFractionDigits: 0,
    }).format(value);
  }

  function calculate() {
    const mktyCount = Math.max(1, Math.min(10, Number(mktySelect.value) || 1));
    const applicant = applicantSelect.value;
    const quantity = Math.max(1, Math.min(10, Number(quantityInput.value) || 1));
    const benefit = benefitSelect.value;

    const base = BASE_FEE[applicant] || BASE_FEE.individual;
    const extraClasses = Math.max(0, mktyCount - 1) * EXTRA_CLASS_FEE;
    const subtotal = base + extraClasses;
    const coefficient = BENEFIT_COEFFICIENT[benefit] ?? 1;
    const total = subtotal * coefficient * quantity;

    feeTotal.textContent = formatMoney(total);
    feeBase.textContent = formatMoney(base * coefficient);
    feeExtra.textContent = formatMoney(extraClasses * coefficient);

    // Обновляем подсказку по МКТУ
    mktyHint.textContent = MKTY_DESCRIPTIONS[mktyCount] || "Описание для выбранного класса отсутствует.";
  }

  // Слушатели событий
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("input", calculate);
  form.addEventListener("change", calculate);

  saveButton.addEventListener("click", () => {
    const total = feeTotal.textContent;
    alert(`Расчёт сохранён!\nИтоговая пошлина: ${total}`);
    // Здесь можно добавить логику сохранения на сервере:
    // fetch("/api/v1/public/calculations", { method: "POST", body: ... })
  });

  // Первый расчёт при загрузке
  calculate();
});