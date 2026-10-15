document.addEventListener("DOMContentLoaded", () => {
  const dropzone = document.querySelector("#upload-dropzone");
  const fileInput = document.querySelector("#file-input");
  const chooseBtn = document.querySelector("#choose-files-btn");
  const checkBtn = document.querySelector("#check-btn");
  const uploadStatus = document.querySelector("#upload-status");
  const matchesList = document.querySelector("#matches-list");
  const plagiarismValue = document.querySelector("#plagiarism-value");

  let selectedFiles = [];
  let isChecking = false;

  // --- Работа с файлами ---
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " Б";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " КБ";
    return (bytes / (1024 * 1024)).toFixed(1) + " МБ";
  }

  function renderFiles() {
    uploadStatus.replaceChildren();
    if (!selectedFiles.length) {
      uploadStatus.textContent = "";
      checkBtn.disabled = true;
      return;
    }
    for (const file of selectedFiles) {
      const row = document.createElement("div");
      row.className = "file-item";
      const name = document.createElement("strong");
      name.textContent = file.name;
      const size = document.createElement("span");
      size.textContent = formatSize(file.size);
      row.append(name, size);
      uploadStatus.append(row);
    }
    checkBtn.disabled = false;
  }

  function addFiles(files) {
    const allowed = [".mp3", ".wav", ".flac", ".m4a"];
    for (const file of files) {
      const name = file.name.toLowerCase();
      const ok = allowed.some((ext) => name.endsWith(ext)) || file.type.startsWith("audio/");
      if (!ok) continue;
      if (selectedFiles.some((f) => f.name === file.name && f.size === file.size)) continue;
      selectedFiles.push(file);
    }
    renderFiles();
  }

  // --- Клик по dropzone ---
  dropzone.addEventListener("click", () => fileInput.click());
  chooseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  // --- Drag & Drop ---
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  });

  // --- Проверка (демо) ---
  // Здесь имитируется результат. Замените на реальный API-запрос.
  const DEMO_MATCHES = [
    { title: "Midnight Echoes", author: "The Velvet Waves", probability: 78 },
    { title: "Sunset Boulevard", author: "L. Marlow", probability: 42 },
  ];

  function getRandomProbability() {
    return Math.floor(Math.random() * 70) + 25;
  }

  function renderMatches(matches, overall) {
    matchesList.replaceChildren();
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.className = "matches-empty";
      empty.textContent = "Совпадений не найдено. Ваш трек уникален 🎉";
      matchesList.append(empty);
    } else {
      for (const match of matches) {
        const item = document.createElement("div");
        item.className = "match-item";

        const title = document.createElement("p");
        title.className = "match-item-title";
        title.textContent = match.title;

        const author = document.createElement("p");
        author.className = "match-item-author";
        author.textContent = "Автор: " + match.author;

        const probability = document.createElement("p");
        probability.className = "match-item-probability";
        probability.textContent = "Совпадение: " + match.probability + "%";

        item.append(title, author, probability);
        matchesList.append(item);
      }
    }

    // Обновляем итоговую вероятность
    plagiarismValue.textContent = overall + "%";
    plagiarismValue.classList.remove("is-low", "is-medium", "is-high");
    if (overall < 30) plagiarismValue.classList.add("is-low");
    else if (overall < 60) plagiarismValue.classList.add("is-medium");
    else plagiarismValue.classList.add("is-high");
  }

  // Начальное состояние
  renderMatches([], 0);
  plagiarismValue.textContent = "—";
  plagiarismValue.classList.remove("is-low", "is-medium", "is-high");

  // --- Кнопка "Проверить" ---
  checkBtn.addEventListener("click", () => {
    if (isChecking || !selectedFiles.length) return;
    isChecking = true;
    checkBtn.disabled = true;
    checkBtn.textContent = "Проверяем…";

    // Имитация задержки запроса
    setTimeout(() => {
      // Здесь вы можете отправить файлы на реальный сервер:
      // const formData = new FormData();
      // for (const file of selectedFiles) formData.append("files", file);
      // fetch("/api/v1/public/check", { method: "POST", body: formData })...

      const random = Math.random();
      let matches, overall;

      if (random < 0.25) {
        // Уникальный трек
        matches = [];
        overall = Math.floor(Math.random() * 15) + 3;
      } else {
        // Найдены совпадения
        matches = DEMO_MATCHES.map((m) => ({ ...m, probability: getRandomProbability() }));
        overall = Math.floor(Math.random() * 40) + 45;
      }

      renderMatches(matches, overall);
      isChecking = false;
      checkBtn.disabled = false;
      checkBtn.textContent = "Проверить ещё раз";
    }, 1200);
  });
});