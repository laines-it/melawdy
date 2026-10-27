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
  const matches = document.querySelector("#matches-list");
  const summary = document.querySelector("#result-summary");
  const audio = document.querySelector("#query-audio");
  const download = document.querySelector("#download-result");
  const recordStart = document.querySelector("#record-start");
  const recordStop = document.querySelector("#record-stop");
  const recordCancel = document.querySelector("#record-cancel");
  const recordStatus = document.querySelector("#record-status");
  const recordTime = document.querySelector("#record-time");
  const recordPreview = document.querySelector("#record-preview");
  const MIN_RECORD_SECONDS = 20, MAX_RECORD_SECONDS = 300;
  const recordingFormat = typeof MediaRecorder !== "undefined" && navigator.mediaDevices?.getUserMedia && window.isSecureContext !== false
    ? ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4;codecs=mp4a.40.2", "audio/mp4"]
      .find((type) => MediaRecorder.isTypeSupported(type)) : null;
  let capture = null, recordingURL = null, leaving = false;
  const STORAGE_KEY = "melawdy-clews-demo-job";
  const labels = { uploading: "Загрузка файла…", queued: "Ожидает ручного запуска оператором",
    processing: "Оператор запустил обработку", completed: "Обработка завершена", failed: "Обработка не выполнена" };
  let capability, file, job, timer, objectURL, clipEnd, busy = false, pollErrors = 0;
  let renderVersion = 0;
  const previewPlayers = [], previewURLs = [];
  function clearPreviews() {
    renderVersion++;
    previewPlayers.splice(0).forEach((player) => { player.pause(); player.removeAttribute("src"); player.load(); });
    previewURLs.splice(0).forEach((url) => URL.revokeObjectURL(url));
  }

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
  function selectFile(candidate, fromRecording = false) {
    if (busy || capture || !capability?.available || !candidate) return;
    if (!/\.(mp3|wav|flac|ogg|m4a|aac|webm)$/i.test(candidate.name)) {
      file = null; submit.disabled = true; selected.textContent = "";
      status.textContent = "Выберите MP3, WAV, FLAC, OGG, M4A, AAC или WebM."; return;
    }
    if (!candidate.size || candidate.size > capability.max_upload_mb * 1024 * 1024) {
      file = null; submit.disabled = true; selected.textContent = "";
      status.textContent = `Файл должен быть непустым и не больше ${capability.max_upload_mb} МБ.`; return;
    }
    if (!fromRecording) {
      clearRecordingPreview(); recordTime.hidden = true;
      recordStart.textContent = "🎙 Записать с микрофона";
      if (recordingFormat) recordStatus.textContent = "Запишите от 20 секунд до 5 минут музыки, затем отправьте запись на проверку.";
    }
    file = candidate;
    selected.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} МБ`;
    submit.disabled = false;
    status.textContent = "Файл выбран. Нажмите «Отправить на проверку».";
  }
  function previewFile(blob) {
    if (objectURL) URL.revokeObjectURL(objectURL);
    const types = { mp3: "audio/mpeg", wav: "audio/wav", flac: "audio/flac", ogg: "audio/ogg", m4a: "audio/mp4", aac: "audio/aac", webm: "audio/webm" };
    const extension = (job?.filename || file?.name || "").split(".").pop().toLowerCase();
    objectURL = URL.createObjectURL(new Blob([blob], { type: types[extension] || blob.type }));
    audio.src = objectURL;
    audio.hidden = false;
    clipEnd = undefined;
  }
  function syncControls() {
    const locked = busy || !!capture || !capability?.available;
    choose.disabled = input.disabled = locked;
    submit.disabled = locked || !file;
    recordStart.disabled = locked || !recordingFormat;
    recordStop.hidden = recordCancel.hidden = !capture;
    recordStop.disabled = !capture?.recorder || capture.recorder.state !== "recording";
  }
  function clearRecordingPreview() {
    recordPreview.pause(); recordPreview.hidden = true;
    recordPreview.removeAttribute("src"); recordPreview.load();
    if (recordingURL) URL.revokeObjectURL(recordingURL);
    recordingURL = null;
  }
  function releaseCapture(current) {
    clearInterval(current.interval); clearTimeout(current.timeout);
    current.stream?.getTracks().forEach((track) => track.stop());
  }
  function stopRecording(current) {
    if (capture !== current || !current.recorder || current.recorder.state !== "recording") return;
    current.stoppedAt = Date.now();
    current.recorder.stop();
    recordStop.disabled = true;
  }
  function cancelRecording() {
    const current = capture;
    if (!current) return;
    capture = null; current.cancelled = true;
    if (current.recorder && current.recorder.state !== "inactive") current.recorder.stop();
    releaseCapture(current); syncControls();
    recordStatus.textContent = "Запись отменена.";
    recordTime.hidden = true;
  }
  function finishRecording(current) {
    releaseCapture(current);
    if (capture !== current || current.cancelled || leaving) return;
    capture = null; syncControls();
    const seconds = ((current.stoppedAt || Date.now()) - current.startedAt) / 1000;
    recordTime.textContent = clock(seconds);
    if (current.error) { recordStatus.textContent = "Запись прервалась. Попробуйте записать ещё раз."; return; }
    if (seconds < MIN_RECORD_SECONDS) {
      recordStatus.textContent = "Запись короче 20 секунд. Запишите более длинный отрывок."; return;
    }
    if (seconds > MAX_RECORD_SECONDS + 1) {
      recordStatus.textContent = "Запись превысила 5 минут. Запишите более короткий отрывок."; return;
    }
    if (!current.bytes || current.bytes > capability.max_upload_mb * 1024 ** 2) {
      recordStatus.textContent = `Запись пустая или превышает ${capability.max_upload_mb} МБ. Запишите более короткий отрывок.`; return;
    }
    const mime = current.recorder.mimeType || recordingFormat;
    const extension = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a" }[mime.split(";")[0]];
    if (!extension) { recordStatus.textContent = "Браузер записал неподдерживаемый формат. Загрузите аудиофайл."; return; }
    const recording = new File(current.chunks, `recording-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`, { type: mime });
    clearRecordingPreview();
    recordingURL = URL.createObjectURL(recording);
    recordPreview.src = recordingURL; recordPreview.hidden = false;
    selectFile(recording, true);
    recordStatus.textContent = "Запись готова. Прослушайте её и нажмите «Отправить на проверку».";
    recordStart.textContent = "🎙 Записать ещё раз";
  }
  recordStart.addEventListener("click", async () => {
    if (!recordingFormat || capture || busy || !capability?.available) return;
    const current = { chunks: [], bytes: 0, stream: null, recorder: null };
    capture = current; syncControls();
    recordTime.hidden = true;
    recordStatus.textContent = "Разрешите доступ к микрофону в браузере.";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false,
      });
      if (capture !== current || current.cancelled || leaving) { stream.getTracks().forEach((track) => track.stop()); return; }
      current.stream = stream;
      current.recorder = new MediaRecorder(stream, { mimeType: recordingFormat, audioBitsPerSecond: 128000 });
      current.recorder.addEventListener("dataavailable", (event) => {
        if (capture !== current || current.cancelled) return;
        if (event.data?.size) { current.chunks.push(event.data); current.bytes += event.data.size; }
        if (current.bytes >= capability.max_upload_mb * 1024 ** 2 || Date.now() - current.startedAt >= MAX_RECORD_SECONDS * 1000) stopRecording(current);
      });
      current.recorder.addEventListener("stop", () => finishRecording(current));
      current.recorder.addEventListener("error", () => {
        current.error = true;
        stopRecording(current);
        finishRecording(current);
      });
      stream.getTracks().forEach((track) => track.addEventListener("ended", () => stopRecording(current)));
      audio.pause(); recordPreview.pause(); previewPlayers.forEach((player) => player.pause());
      current.startedAt = Date.now();
      current.recorder.start(1000);
      recordTime.hidden = false; recordTime.textContent = "00:00";
      const tick = () => {
        const seconds = (Date.now() - current.startedAt) / 1000;
        recordTime.textContent = clock(seconds);
        const message = seconds < MIN_RECORD_SECONDS
          ? "Идёт запись… Запишите не менее 20 секунд музыки."
          : "Идёт запись… Нажмите «Остановить запись», когда закончите.";
        if (recordStatus.textContent !== message) recordStatus.textContent = message;
      };
      tick(); current.interval = setInterval(tick, 1000);
      current.timeout = setTimeout(() => stopRecording(current), MAX_RECORD_SECONDS * 1000);
      syncControls();
    } catch (error) {
      releaseCapture(current);
      if (capture !== current) return;
      capture = null; syncControls();
      recordStatus.textContent = error.name === "NotAllowedError"
        ? "Доступ к микрофону запрещён. Разрешите его в настройках сайта в браузере."
        : error.name === "NotFoundError" ? "Микрофон не найден. Подключите его или загрузите аудиофайл."
        : "Не удалось начать запись. Проверьте микрофон или загрузите аудиофайл.";
    }
  });
  recordStop.addEventListener("click", () => { if (capture) stopRecording(capture); });
  recordCancel.addEventListener("click", cancelRecording);
  if (!recordingFormat) recordStatus.textContent = "Запись с микрофона недоступна. Откройте сайт по HTTPS в поддерживаемом браузере или загрузите файл.";

  function showJob() {
    jobPanel.hidden = false;
    jobNumber.value = job.code || job.id;
    document.querySelector("#job-state").textContent = labels[job.status] || job.status;
    document.querySelector("#job-filename").textContent = job.filename || "";
    document.querySelector("#job-expiry").textContent = `Файл и результат хранятся до ${new Date(job.expires_at * 1000).toLocaleString("ru-RU")}.`;
    clearPreviews();
    matches.replaceChildren();
    download.hidden = !job.result;
    summary.textContent = "";
    if (!job.result) return;
    const result = job.result;
    summary.textContent = result.outcome === "failed"
      ? result.message || "Обработка не выполнена. Оператор может повторить запуск."
      : `Проверено записей: ${result.catalog_size}. Окно: ${result.window_seconds} с, шаг: ${result.hop_seconds} с.`;
    if (result.message && result.outcome !== "failed") summary.textContent += ` ${result.message}`;
    result.matches.slice(0, 3).forEach((match, index) => {
      const card = element("article", ""); card.className = "match-item";
      const title = element("h3", match.reference); title.className = "match-item-title";
      const timing = element("p", `Ваша запись: ${clock(match.query_start)}–${clock(match.query_end)}. Найденная: ${clock(match.reference_start)}–${clock(match.reference_end)}.`);
      // A display index, not a calibrated probability; raw distance stays in JSON reports.
      const percent = Math.round((1 - match.distance / 3) * 100 * 10) / 10;
      const tier = percent >= 75 ? "high" : percent >= 50 ? "medium" : "low";
      const level = { high: "Значительное", medium: "Частичное", low: "Незначительное" }[tier];
      card.className = `match-item match-item--${tier}`;
      const similarity = element("p", `Сходство: ${percent.toLocaleString("ru-RU")}% · ${level}`);
      similarity.className = "match-similarity";
      const play = element("button", "Послушать мой отрывок"); play.type = "button";
      play.addEventListener("click", () => {
        previewPlayers.forEach((player) => player.pause());
        audio.currentTime = match.query_start; clipEnd = match.query_end;
        audio.play().catch(() => { status.textContent = "Браузер не воспроизводит этот формат. Скачайте исходный файл или используйте MP3."; });
      });
      card.append(title, timing, similarity, play);
      if (match.preview_available) {
        const referenceAudio = element("audio", "");
        referenceAudio.controls = true; referenceAudio.preload = "none"; referenceAudio.hidden = true;
        referenceAudio.setAttribute("aria-label", `Найденный отрывок: ${match.reference}`);
        const listen = element("button", "Послушать найденный отрывок"); listen.type = "button";
        const previewStatus = element("p", ""); previewStatus.setAttribute("role", "status");
        const version = renderVersion;
        previewPlayers.push(referenceAudio);
        referenceAudio.addEventListener("play", () => {
          audio.pause(); clipEnd = undefined;
          previewPlayers.forEach((player) => { if (player !== referenceAudio) player.pause(); });
        });
        listen.addEventListener("click", async () => {
          listen.disabled = true; previewStatus.textContent = "Загружаем найденный отрывок…";
          try {
            if (!referenceAudio.src) {
              const blob = await request(`music-check/jobs/${job.id}/matches/${index}/audio`,
                { headers: headers(), responseType: "blob" });
              if (version !== renderVersion) return;
              const url = URL.createObjectURL(new Blob([blob], { type: "audio/mpeg" }));
              previewURLs.push(url); referenceAudio.src = url;
            }
            referenceAudio.hidden = false; referenceAudio.currentTime = 0;
            await referenceAudio.play(); previewStatus.textContent = "";
          } catch (error) {
            previewStatus.textContent = error.message || "Не удалось воспроизвести отрывок. Используйте плеер ниже.";
          } finally { listen.disabled = false; }
        });
        referenceAudio.addEventListener("error", () => { previewStatus.textContent = "Браузер не смог воспроизвести MP3-отрывок."; });
        card.append(listen, previewStatus, referenceAudio);
      } else {
        card.append(element("p", "Аудио найденного отрывка не передано. Для прослушивания повторите проверку в обновлённом ноутбуке."));
      }
      matches.append(card);
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
        summary.textContent = "Задание недоступно. Отправьте запись заново.";
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
    try { await navigator.clipboard.writeText(job.code || job.id); status.textContent = "Номер задания скопирован."; }
    catch { jobNumber.select(); status.textContent = "Выделенный номер можно скопировать вручную."; }
  });
  submit.addEventListener("click", async () => {
    if (!file || busy || capture) return;
    busy = true; syncControls();
    stopPolling();
    status.textContent = "Загружаем файл…";
    try {
      const next = await request("music-check/jobs", { method: "POST", body: file,
        headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) } });
      job = next; remember(); previewFile(file); showJob(); updateJob();
    } catch (error) { status.textContent = error.message; if (job) timer = setTimeout(updateJob, 5000); }
    finally { busy = false; syncControls(); }
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
      syncControls();
      dropzone.setAttribute("aria-disabled", "false");
      document.querySelector("#upload-instructions").textContent = `Максимальный размер записи - ${capability.max_upload_mb} МБ.`;
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
  window.addEventListener("pageshow", () => { leaving = false; syncControls(); });
  window.addEventListener("pagehide", () => { leaving = true; cancelRecording(); clearRecordingPreview(); stopPolling(); clearPreviews(); if (objectURL) URL.revokeObjectURL(objectURL); });

});
