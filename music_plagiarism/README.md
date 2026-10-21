# Отдельная проверка музыкальных совпадений Mippia

Локальная программа для ручной проверки модуля. Внутри — код
`Mippia/Music-Plagiarism-Detection`, commit
`109c703242546e88914d8dbf04311e06bc3113cb`, с адаптацией для CPU.
Она не импортирует код MeLawDy, не использует его базу, API, `.env` или Docker Compose.

Два режима:

- `compare` — распознать вокальные ноты в своих аудиофайлах и сравнить их.
- `compare-json` — проверить тот же оригинальный алгоритм на готовых нотных JSON,
  без Demucs и повторного распознавания. Включены синтетические примеры.

Результаты — JSON и HTML с оценкой сходства и временем совпавших фрагментов.
HTML открывается обычным браузером; для своих аудиофайлов он содержит плееры.
Сравнение идёт только с указанными эталонами, не со всей музыкой в интернете.

## Запуск через Docker (Linux, macOS, Windows)

Для первого запуска нужен интернет: сборка получает зависимости, а Demucs
при первом распознавании загружает свои модели. Пользовательское аудио
обрабатывается локально и не отправляется в Mippia API.
Образ рассчитан на CPU; для долгих записей обработка может занимать много времени.
По умолчанию Demucs обрабатывает окна по 2 секунды для ограничения памяти.
Если памяти достаточно, можно указать `--separation-segment 5` или до 7 с;
длина окна влияет на качество разделения и расход RAM. Даже короткие окна
требуют заметно больше памяти, чем режим `compare-json`.
Окружение проверяется на Linux x86-64. На Apple Silicon для сборки и запуска
этого набора CPU-колёс добавьте `--platform linux/amd64` к командам Docker.

Откройте терминал **в этой папке**, `music_plagiarism`.
Сначала получите две небольшие модели Mippia и соберите отдельный образ:

```sh
python3 run.py weights
docker build -t melawdy-music-plagiarism:local .
```

На Windows вместо `python3` можно использовать `py -3`.
Команда `weights` работает без Python-пакетов ML; требуется Python 3.11+.
Веса проверяются по размеру и SHA-256. Они не хранятся в Git.

Linux/macOS: проверка окружения и запуск примера без аудио:

```sh
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local doctor
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local compare-json examples/query.json --reference examples/same_melody.json --reference examples/different.json --output results/example.json
```

PowerShell:

```powershell
docker run --rm -v "${PWD}:/data" melawdy-music-plagiarism:local doctor
docker run --rm -v "${PWD}:/data" melawdy-music-plagiarism:local compare-json examples/query.json --reference examples/same_melody.json --reference examples/different.json --output results/example.json
```

Откройте `results/example.html`. Одинаковая мелодия должна получить оценку выше,
чем пример `different`. Дополнительные примеры: `octave_up.json` (та же мелодия
на октаву выше) и `no_notes.json` (без нот).
Эти данные проверяют механику алгоритма и не измеряют точность на реальной музыке.

### Сравнить свои аудиофайлы

Создайте папку `input` и положите туда `my_song.mp3` и `reference.mp3`.
Желательно начать с фрагментов по 30–60 секунд с вокалом и чётким ритмом.
Поддерживаются форматы, которые декодирует ffmpeg, включая WAV/MP3/FLAC/M4A.

Linux/macOS:

```sh
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local compare input/my_song.mp3 --reference input/reference.mp3 --device cpu --output results/my_check.json
```

PowerShell:

```powershell
docker run --rm -v "${PWD}:/data" melawdy-music-plagiarism:local compare input/my_song.mp3 --reference input/reference.mp3 --device cpu --output results/my_check.json
```

Несколько эталонов — повторите `--reference`:

```sh
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local compare input/my_song.mp3 --reference input/reference.mp3 --reference input/another.wav --output results/catalog_check.json
```

В Docker указывайте пути внутри `/data` или относительные пути, как выше.
Файлы за пределами смонтированной папки контейнер не видит.
На Linux создаваемые контейнером отчёты могут принадлежать root;
для своего UID/GID добавьте `--user "$(id -u):$(id -g)"` к `docker run`.

Распознавание кэшируется в `.cache/transcriptions` по содержимому файла и версии
адаптера. При повторном сравнении тех же файлов оно не выполняется заново.
Ключ кэша учитывает устройство и длину окна Demucs. Кэш содержит извлечённые
ноты, а не копии исходных аудиофайлов.
При изменении моделей/параметров распознавания удалите соответствующий кэш
или задайте другую папку через `--cache-dir`.

### Сохранить распознанные ноты отдельно

```sh
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local transcribe input/my_song.mp3 --output results/my_notes.json
docker run --rm -v "$PWD:/data" melawdy-music-plagiarism:local compare-json results/my_notes.json --reference examples/same_melody.json --output results/notes_check.json
```

## Без Docker: собственное Python-окружение

Используйте Python 3.11 или 3.12, не окружение сайта.
На Linux для полной аудиоцепочки нужны ffmpeg, libsndfile, C/C++ compiler.
На Windows для сборки madmom удобнее использовать Docker или WSL.

Только сравнение готовых JSON:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install torch==2.5.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py doctor --comparator-only
.venv/bin/python run.py compare-json examples/query.json --reference examples/same_melody.json --reference examples/different.json --output results/example.json
```

Для аудио дополнительно:

```sh
.venv/bin/python -m pip install setuptools==75.6.0 wheel==0.45.1 Cython==3.0.11 numpy==1.26.4
.venv/bin/python -m pip install torchaudio==2.5.1+cpu torchvision==0.20.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install --no-build-isolation -r requirements-audio.txt
.venv/bin/python install_madmom_metadata.py
.venv/bin/python run.py weights
.venv/bin/python run.py doctor
.venv/bin/python run.py compare input/my_song.mp3 --reference input/reference.mp3 --output results/my_check.json
```

В собственной CUDA-среде можно выбрать `--device cuda` или `--device auto`;
нужно самостоятельно установить совместимые CUDA-сборки torch/torchaudio/torchvision.
Включённый Docker-образ использует CPU.

## Как читать результат

- `matches[].score` — максимальное сходство пары вокальных фрагментов в диапазоне 0–1.
- `top_segments` — лучшие пары с началом и концом фрагмента в запросе и эталоне.
- `no_query_segments` — в запросе нет пригодных фрагментов: например, нет вокальных
  нот или мало полных тактов.
- `no_reference_segments` — эталоны не содержат пригодных фрагментов.
- Ошибка распознавания/формата/окружения выводится в терминал, exit code 2.
  `doctor` возвращает 1, если окружение неполное.

Не интерпретируйте балл как процент вероятности плагиата. Алгоритм сравнивает
вокальную мелодию, ритм и темп, работает с четырёхтактовыми окнами в размере 4/4.
Chroma убирает разницу октав, но автоматической проверки всех тональностей нет.
Одинаковые или распространённые музыкальные обороты тоже могут давать высокие
оценки. Инструментальные заимствования и права на произведение модуль не проверяет.

## Проверки программы

В отдельном Docker-окружении:

```sh
docker run --rm --network none -v "$PWD:/data" --entrypoint python melawdy-music-plagiarism:local -m unittest discover -s tests -v
```

Только comparator в локальном venv:

```sh
.venv/bin/python -m unittest discover -s tests -p test_comparison.py -v
```

Проверяются ранжирование одинаковой/другой мелодии, инвариантность к октаве,
разные размеры батчей, отсутствие нот, неверные данные и запись отчётов.
Полный набор дополнительно загружает реальные checkpoint в архитектуры моделей
и выполняет прямой проход AST. Это технические проверки, не оценка качества
распознавания реальной музыки.

Версии пакетов собранного и проверенного окружения сохранены в
`environment-tested.txt`. Веса AST содержат несколько неиспользуемых старых
слоёв; тест проверяет наличие всех нужных слоёв и допускает только эти известные
лишние ключи, как в исходном загрузчике Mippia.

Лицензии, происхождение и список изменений: `NOTICE.md`, `LICENSE`, `UPSTREAM.json`.
