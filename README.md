# MeLawDy

Стартовый каркас сайта MeLawDy: статический web, один Python API на FastAPI, PostgreSQL с pgvector и MinIO. Код поиска и ранжирования лежит в `ml/` и вызывается внутри API без отдельного сетевого сервиса.

## Запуск

Нужны Docker Engine и Docker Compose v2. После клонирования репозитория из корня проекта:

```sh
docker compose up --build
```

`.env` для локального запуска необязателен. Чтобы изменить порты или учётные данные, скопируйте `.env.example` в `.env` и отредактируйте значения.
Если вы ранее запускали версию с отдельным `ml`-контейнером, один раз выполните `docker compose down --remove-orphans` перед новым запуском; данные в томах при этом сохранятся.

- Сайт: http://localhost:8080
- Панель администратора: http://localhost:8080/admin.html
- API и документация OpenAPI: http://localhost:8081/docs
- MinIO Console: http://localhost:9001
- MinIO S3 API: http://localhost:9000
- PostgreSQL: `localhost:5432`, база `melawdy`, пользователь `melawdy_app`

Nginx передаёт `/api/` в Python API. Все опубликованные порты привязаны к `127.0.0.1` хоста. Для доступа из интернета потребуется отдельная настройка домена, TLS и reverse proxy.

Nginx обновляет IP сервиса `api` через DNS с интервалом кэша 5 секунд. DNS-серверы берутся из `/etc/resolv.conf` контейнера при запуске; для Kubernetes имя API дополняется доменом текущего namespace из DNS search-списка. При необходимости hostname можно задать через `NGINX_API_HOST`. Пересоздание API-контейнера не требует перезапуска web. После обновления этого конфига пересоберите web: `docker compose up --build -d web`.

Развёртывание на VPS с доменом `lawmposer.ru`, HTTPS и отдельным namespace существующего k3s описано в [инструкции VPS](deploy/k3s/README.md). Локальный Compose работает независимо от него. Push в `main` автоматически обновляет VPS после успешных тестов GitHub Actions; текущий SHA сайта доступен в `https://lawmposer.ru/version.json`. Другие ветки публикуются после слияния в `main`.

## Запуск на Windows

Установите и запустите [Docker Desktop с WSL 2](https://docs.docker.com/desktop/features/wsl/), используя Linux containers. Dockerfile и `backend/entrypoint.sh` выполняются внутри Linux-контейнера; локальная установка Python или ручной запуск `.sh` через PowerShell не нужны.

Из корня проекта в PowerShell:

```powershell
docker info --format '{{.OSType}}'
docker compose up --build -d
docker compose ps -a
```

Первая команда должна вывести `linux`. После запуска откройте http://localhost:8080. Ключ `-d` запускает контейнеры в фоне; без него терминал остаётся занят выводом логов — это нормальная работа Compose.

`.gitattributes` закрепляет LF для shell-скриптов; Dockerfile дополнительно исправляет CRLF в `entrypoint.sh` при сборке, включая старые рабочие копии Windows. После получения этих изменений пересоберите API командой `docker compose up --build -d`.

Если сайт не открывается, сохраните вывод следующих команд:

```powershell
docker compose ps -a
docker compose logs --tail=100 api postgres web minio
```

Если проблема возникает при сборке, отдельно выполните `docker compose --progress plain build` и сохраните последние строки вывода. Ошибки скачивания образов или пакетов требуют проверки сети Docker Desktop; смена `entrypoint.sh` их не исправляет.

## Управление

```sh
# Остановить контейнеры, сохранив PostgreSQL и MinIO
docker compose down

# Пересобрать и запустить в фоне
docker compose up --build -d

# Смотреть логи
docker compose logs -f
```

`docker compose down -v` дополнительно удаляет локальные данные PostgreSQL и MinIO.

## Администратор и базовый интерфейс

Интерфейс состоит из обычных HTML-полей без оформления. Главная страница показывает опубликованные статьи и активные assessment-опросы. В админ-панели доступны создание, редактирование и удаление статей, категорий, тегов, терминов, Q&A, опросов, вопросов, вариантов, результатов, правил, шаблонов и справочников пошлин.

Для новой установки создайте первого администратора после запуска контейнеров:

```sh
docker compose exec api python -m backend.manage_admin --generate-password --credentials-file /tmp/melawdy-admin-credentials
docker compose cp api:/tmp/melawdy-admin-credentials .admin-credentials
chmod 600 .admin-credentials
docker compose exec api rm /tmp/melawdy-admin-credentials
```

Email по умолчанию — `admin@melawdy.local`. Сгенерированный пароль находится в `.admin-credentials`; файл исключён из Git и Docker-контекста. Для уже существующего администратора команда сохраняет прежний пароль. Если Python-окружение настроено локально и PostgreSQL доступен на `localhost:5432`, достаточно `python -m backend.manage_admin --generate-password`.

Альтернатива для автоматического создания: задайте `ADMIN_EMAIL`, `ADMIN_PASSWORD` (минимум 5 символов) и `ADMIN_FULL_NAME` в локальном `.env`, затем пересоздайте API. Пустой `ADMIN_PASSWORD` отключает автоматическое создание; существующий пароль не перезаписывается.

Порядок заполнения статей и assessment, команды смены пароля и описание доступа — в [инструкции администратора](docs/admin.md). Assessment пока можно редактировать и просматривать: прохождение с сохранением ответов и вычислением результата ещё не реализовано.

## Тесты

Локально, из корня проекта:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt
python -m pytest -q
```

Регрессионная проверка Nginx при смене IP API выполняется отдельно с Docker: `python -m pytest -q backend/tests/infrastructure/test_nginx_dns.py`. Она создаёт временную сеть и контейнеры, проверяет GET и POST без перезапуска web и удаляет тестовые ресурсы; рабочая БД не используется.

Локальные юнит-тесты выполняются полностью в Python. Они проверяют схемы, функции API, репозиторий с mock-сессией, вход, права администратора, CSRF и сохранение материалов; подключение к базе данных, Docker и запущенная PostgreSQL не нужны.

GitHub Actions запускает этот же набор Python-тестов на `push`, `pull_request`, `merge_group` и вручную. Отдельный CI job поднимает PostgreSQL с pgvector, применяет миграции, сверяет схему с моделями и проверяет связи, JSONB, деньги, поиск вектора и откат/повторное применение миграции. Он не входит в локальный запуск `python -m pytest`.

## Структура

```text
web/          интерфейс и Nginx reverse proxy
backend/      FastAPI, SQLAlchemy-модели, схемы запросов и доступ к БД
ml/           TF-IDF, локальные embeddings, индексация и поиск по контенту
migrations/   версионированные Alembic-миграции
deploy/       Dockerfile для PostgreSQL/MinIO и заметки для деплоя
docs/         исходная ER-схема, принятые допущения и инструкции по поиску
```

`web/static/index.html` и `web/static/admin.html` используют обычные HTML-элементы и JavaScript без дополнительного frontend-фреймворка.

## Данные и миграции

Утверждённый стек: Python, FastAPI, SQLAlchemy 2, psycopg 3 и Alembic. В `backend/models/` представлены все 24 таблицы из [ER-схемы](docs/schema.mmd): пользователи, контент, опросы, пошлины, шаблоны, документы и история. Связи доступны как Python-объекты. Подробности типов, ограничений и предложенных enum-значений — в [описании базы](docs/database.md).

Новая миграция `0002_domain_schema` добавляет доменную схему. Старые UUID-таблицы `documents` и `document_chunks` сохраняются с данными; прежний `/api/v1/documents` продолжает работать с ними. Перенос в `user_documents` не выполняется автоматически: у старых записей нет владельца, типа документа и остальных обязательных полей новой схемы.

Миграция `0003_admin_sessions` добавляет серверные сессии администратора. Пароли хранятся как Argon2id-хеши, в базе сохраняется только хеш токена сессии. Операции изменения в админ-API и создание legacy-документа требуют действующую сессию администратора и CSRF-токен.

API выполняет `alembic upgrade head` при запуске. Это применяет недостающие миграции и к уже существующему тому PostgreSQL. Пример: `docker compose run --rm api alembic current` показывает текущую ревизию.

Для Python-окружения с доступом к PostgreSQL:

```sh
python -m alembic upgrade head
python -m alembic current
```

`content_item_chunks.embedding` хранит `vector(1024)` для `Roflmax/bge-m3-russian-legal`, индекс HNSW использует cosine distance. TF-IDF выполняется через scikit-learn. Установка модели на VPS, предварительный расчёт embeddings и команды поиска описаны в [инструкции по поиску](docs/search.md). Веса и PyTorch не требуются для обычного запуска и юнит-тестов.

`POST /api/v1/documents`, `GET /api/v1/documents` и `GET /api/v1/documents/{id}` — минимальный пример работы с записями. `POST /api/v1/analyze` пока явно сообщает, что ML-пайплайн не настроен. MinIO запущен как хранилище, но загрузка файлов ещё не реализована.

Учётные данные в Compose предназначены только для локальной разработки. Перед публикацией задайте отдельные секреты, настройте TLS, доступ к MinIO и резервное копирование данных.
