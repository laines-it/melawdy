document.addEventListener("DOMContentLoaded", async () => {
  const request = window.MelawdyAPI.request;
  const status = document.querySelector("#upload-status");
  const input = document.querySelector("#file-input");
  const choose = document.querySelector("#choose-files-btn");
  const submit = document.querySelector("#check-btn");
  const dropzone = document.querySelector("#upload-dropzone");
  const selected = document.querySelector("#selected-file");
  const jobPanel = document.querySelector("#job-panel");
  const jobNumber = document.querySelector("#job-number");
  const refresh = document.querySelector("#refresh-job");
  const resultHint = document.querySelector("#result-hint");
  const matches = document.querySelector("#matches-list");
  const summary = document.querySelector("#result-summary");
  const audio = document.querySelector("#query-audio");
  const download = document.querySelector("#download-result");
  const STORAGE_KEY = "melawdy-clews-demo-job";
  const labels = { uploading: "Загрузка файла…", queued: "Ожидает ручного запуска оператором",
    processing: "Оператор запустил обработку", completed: "Обработка завершена", failed: "Обработка не выполнена" };
  let capability, file, job, timer, objectURL, clipEnd, busy = false, pollErrors = 0;

  function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }
  function clock(seconds) {
    return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
  }
  function stopPolling() { clearTimeout(timer); timer = null; }
  function remember() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: job.id, access_token: job.access_token })); }
    catch { status.textContent += " Сохранение задания в браузере недоступно — оставьте страницу открытой."; }
  }
  function headers() { return { "X-Music-Job-Token": job.access_token }; }
  function selectFile(candidate) {
    if (busy || !capability?.available || !candidate) return;
    if (!/\.(mp3|wav|flac|ogg|m4a|aac)$/i.test(candidate.name)) {
      file = null; submit.disabled = true; selected.textContent = "";
      status.textContent = "Выберите MP3, WAV, FLAC, OGG, M4A или AAC."; return;
    }
    if (!candidate.size || candidate.size > capability.max_upload_mb * 1024 * 1024) {
      file = null; submit.disabled = true; selected.textContent = "";
      status.textContent = `Файл должен быть непустым и не больше ${capability.max_upload_mb} МБ.`; return;
    }
    file = candidate;
    selected.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} МБ`;
    submit.disabled = false;
    status.textContent = "Файл выбран. Нажмите «Отправить на проверку».";
  }
  function previewFile(blob) {
    if (objectURL) URL.revokeObjectURL(objectURL);
    const types = { mp3: "audio/mpeg", wav: "audio/wav", flac: "audio/flac", ogg: "audio/ogg", m4a: "audio/mp4", aac: "audio/aac" };
    const extension = (job?.filename || file?.name || "").split(".").pop().toLowerCase();
    objectURL = URL.createObjectURL(new Blob([blob], { type: types[extension] || blob.type }));
    audio.src = objectURL;
    audio.hidden = false;
    clipEnd = undefined;
  }
  function showJob() {
    jobPanel.hidden = false;
    jobNumber.value = job.id;
    document.querySelector("#job-state").textContent = labels[job.status] || job.status;
    document.querySelector("#job-filename").textContent = job.filename || "";
    document.querySelector("#job-expiry").textContent = `Файл и результат хранятся до ${new Date(job.expires_at * 1000).toLocaleString("ru-RU")}.`;
    matches.replaceChildren();
    download.hidden = !job.result;
    summary.textContent = "";
    if (!job.result) {
      resultHint.textContent = job.status === "processing"
        ? "Colab обрабатывает запись. Результат появится здесь автоматически."
        : "Передайте номер задания оператору. Обработка начнётся после его ручного запуска.";
      return;
    }
    const result = job.result;
    resultHint.textContent = result.outcome === "failed"
      ? result.message || "Обработка не выполнена. Оператор может повторить запуск."
      : "Ближайшие фрагменты из проверенной коллекции. Меньшее расстояние означает большее сходство; ближайший кандидат может быть несходным.";
    summary.textContent = `Проверено записей: ${result.catalog_size}. Окно: ${result.window_seconds} с, шаг: ${result.hop_seconds} с.`;
    if (result.message && result.outcome !== "failed") summary.textContent += ` ${result.message}`;
    result.matches.forEach((match) => {
      const card = element("article", ""); card.className = "match-item";
      const title = element("h3", match.reference); title.className = "match-item-title";
      const timing = element("p", `Ваша запись: ${clock(match.query_start)}–${clock(match.query_end)}. Найденная: ${clock(match.reference_start)}–${clock(match.reference_end)}.`);
      const distance = element("p", `Расстояние CLEWS: ${match.distance.toFixed(6)}`);
      const play = element("button", "Послушать этот участок моей записи"); play.type = "button";
      play.addEventListener("click", () => {
        audio.currentTime = match.query_start; clipEnd = match.query_end;
        audio.play().catch(() => { status.textContent = "Браузер не воспроизводит этот формат. Скачайте исходный файл или используйте MP3."; });
      });
      card.append(title, timing, distance, play); matches.append(card);
    });
    if (result.outcome === "completed" && !result.matches.length) matches.append(element("p", "Сходные фрагменты не возвращены. Это не вывод об отсутствии заимствований."));
  }
  async function updateJob() {
    if (!job) return;
    stopPolling(); refresh.disabled = true;
    try {
      const current = job.id;
      const next = await request(`music-check/jobs/${current}`, { headers: headers() });
      if (job.id !== current) return;
      job = { ...next, access_token: job.access_token };
      pollErrors = 0; showJob();
      status.textContent = labels[job.status] || job.status;
      if (["queued", "processing", "uploading"].includes(job.status)) timer = setTimeout(updateJob, 5000);
    } catch (error) {
      status.textContent = error.message;
      if (![404, 410, 503].includes(error.status) && ++pollErrors < 5) timer = setTimeout(updateJob, 10000);
      if ([404, 410].includes(error.status)) {
        try { localStorage.removeItem(STORAGE_KEY); } catch {}
        resultHint.textContent = "Задание недоступно. Отправьте запись заново.";
      }
    } finally { refresh.disabled = false; }
  }
  choose.addEventListener("click", () => input.click());
  input.addEventListener("change", () => selectFile(input.files[0]));
  for (const name of ["dragover", "dragleave", "drop"]) dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.toggle("is-dragover", name === "dragover" && !busy);
    if (name === "drop") selectFile(event.dataTransfer.files[0]);
  });
  audio.addEventListener("timeupdate", () => { if (clipEnd !== undefined && audio.currentTime >= clipEnd) { audio.pause(); clipEnd = undefined; } });
  refresh.addEventListener("click", updateJob);
  document.querySelector("#copy-job").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(job.id); status.textContent = "Номер задания скопирован."; }
    catch { jobNumber.select(); status.textContent = "Выделенный номер можно скопировать вручную."; }
  });
  submit.addEventListener("click", async () => {
    if (!file || busy) return;
    busy = true; submit.disabled = choose.disabled = input.disabled = true;
    stopPolling();
    status.textContent = "Загружаем файл…";
    try {
      const next = await request("music-check/jobs", { method: "POST", body: file,
        headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) } });
      job = next; remember(); previewFile(file); showJob(); updateJob();
    } catch (error) { status.textContent = error.message; if (job) timer = setTimeout(updateJob, 5000); }
    finally { busy = false; submit.disabled = !file; choose.disabled = input.disabled = false; }
  });
  download.addEventListener("click", () => {
    const link = element("a", "");
    // The access token is deliberately omitted from exported reports.
    const clean = { ...job }; delete clean.access_token;
    const reportURL = URL.createObjectURL(new Blob([JSON.stringify(clean, null, 2)], { type: "application/json" }));
    link.href = reportURL; link.download = `clews-${job.id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(reportURL), 1000);
  });
  try {
    capability = (await request("public/capabilities")).music_check;
    status.textContent = capability.message;
    if (capability.available) {
      input.disabled = choose.disabled = false;
      dropzone.setAttribute("aria-disabled", "false");
      document.querySelector("#upload-instructions").textContent = `Одна запись от 20 секунд до 30 минут, до ${capability.max_upload_mb} МБ.`;
      try { job = JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch { job = null; }
      if (job?.id && job?.access_token) {
        await updateJob();
        if (job.filename && !["expired"].includes(job.status)) {
          try { previewFile(await request(`music-check/jobs/${job.id}/audio`, { headers: headers(), responseType: "blob" })); }
          catch { /* Results remain readable even if the original audio is unavailable. */ }
        }
      } else { job = null; }
    }
  } catch (error) { status.textContent = error.message; }
  window.addEventListener("pagehide", () => { stopPolling(); if (objectURL) URL.revokeObjectURL(objectURL); });

  const list = document.querySelector("#templates-list"), more = document.querySelector("#more-templates");
  let offset = 0;
  async function loadTemplates() {
    more.disabled = true;
    try {
      const templates = await request(`public/templates?limit=25&offset=${offset}`);
      if (!templates.length && offset === 0) list.textContent = "Шаблоны пока не опубликованы.";
      for (const template of templates) {
        const card = element("div", ""); card.className = "template-card";
        const title = element("h3", template.title); title.className = "template-title";
        const description = element("p", template.description || ""); description.className = "template-desc";
        const link = element("a", "Создать документ →"); link.href = `/documents?template=${encodeURIComponent(template.id)}`; link.className = "template-download";
        card.append(title, description, link); list.append(card);
      }
      offset += templates.length; more.hidden = templates.length < 25;
      document.querySelector("#templates-status").textContent = "";
    } catch (error) { document.querySelector("#templates-status").textContent = error.message; }
    finally { more.disabled = false; }
  }
  more.addEventListener("click", loadTemplates); loadTemplates();
});
