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
- API и документация OpenAPI: http://localhost:8081/docs
- MinIO Console: http://localhost:9001
- MinIO S3 API: http://localhost:9000
- PostgreSQL: `localhost:5432`, база `melawdy`, пользователь `melawdy_app`

Nginx передаёт `/api/` в Python API. Все опубликованные порты привязаны к `127.0.0.1` хоста. Для доступа из интернета потребуется отдельная настройка домена, TLS и reverse proxy.

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

## Тесты

Локально, из корня проекта:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt
python -m pytest -q
```

Локальные юнит-тесты выполняются полностью в Python. Они проверяют схемы, функции API и репозиторий с mock-сессией; подключение к базе данных, Docker и запущенная PostgreSQL не нужны.

GitHub Actions запускает этот же набор Python-тестов на `push`, `pull_request`, `merge_group` и вручную. Отдельный CI job поднимает PostgreSQL с pgvector, применяет миграции и проверяет запись/поиск вектора. Он не входит в локальный запуск `python -m pytest`.

## Структура

```text
web/          интерфейс и Nginx reverse proxy
backend/      FastAPI, SQLAlchemy-модели, схемы запросов и доступ к БД
ml/           место для будущего поиска и ранжирования, сейчас заглушка
migrations/   версионированные Alembic-миграции
deploy/       Dockerfile для PostgreSQL/MinIO и заметки для деплоя
```

Главная страница использует структуру интерфейса [zhkh40](https://github.com/katekitova/zhkh40) как визуальный ориентир: шапку, главный блок с поиском, тематические чипы и карточки. Контент и бренд адаптированы под MeLawDy.

## Данные и миграции

Записи представлены Python-классами `Document` и `DocumentChunk` через SQLAlchemy 2 ORM. Pydantic описывает вход и выход API отдельно. Поле `DocumentChunk.embedding` использует pgvector; размерность пока не закреплена, поскольку модель эмбеддингов ещё не выбрана. Для последующих изменений схемы добавляйте новую ревизию Alembic в `migrations/versions/`.

Для такого слоя данных подходят [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/orm/) и [SQLModel](https://sqlmodel.tiangolo.com/). Здесь выбран SQLAlchemy: он даёт типизированные классы записей, [Alembic](https://alembic.sqlalchemy.org/en/latest/) для версионирования схемы и прямую [интеграцию pgvector](https://github.com/pgvector/pgvector-python#sqlalchemy).

API выполняет `alembic upgrade head` при запуске. Это применяет недостающие миграции и к уже существующему тому PostgreSQL. Пример: `docker compose run --rm api alembic current` показывает текущую ревизию.

`POST /api/v1/documents`, `GET /api/v1/documents` и `GET /api/v1/documents/{id}` — минимальный пример работы с записями. `POST /api/v1/analyze` пока явно сообщает, что ML-пайплайн не настроен. MinIO запущен как хранилище, но загрузка файлов ещё не реализована.

Учётные данные в Compose предназначены только для локальной разработки. Перед публикацией задайте отдельные секреты, настройте TLS, доступ к MinIO и резервное копирование данных.
