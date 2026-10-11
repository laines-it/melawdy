# TF-IDF и embeddings

Тексты и предрасчитанные embeddings хранятся в `content_item_chunks`. Поиск читает только опубликованные материалы с наступившей датой публикации. Команды ниже используют PostgreSQL из `.env` или переменных `POSTGRES_*`.

## TF-IDF

`ml.tfidf.TfidfIndex` использует scikit-learn `TfidfVectorizer` с униграммами/биграммами, L2-нормализацией и cosine similarity. Односимвольные номера статей сохраняются. Матрица разреженная, нулевые совпадения не возвращаются.

```sh
python -m pip install -r backend/requirements.txt
python -m ml.search --mode tfidf --query "авторское право" --limit 5
```

CLI строит TF-IDF по текущему опубликованному корпусу для каждого запуска. Для постоянного процесса класс можно создавать один раз и пересоздавать при изменении состава/текста корпуса. TF-IDF-матрица не записывается в `tsvector` или pgvector: её размер зависит от словаря всего корпуса. Эта реализация предназначена для начального корпуса; загрузка всего корпуса в память потребует пересмотра при росте данных.

## Локальная модель на VPS

Выбрана [Roflmax/bge-m3-russian-legal](https://huggingface.co/Roflmax/bge-m3-russian-legal). Согласно карточке автора: 1024 измерения, максимум 512 токенов, для запроса нужен префикс `Represent this sentence for searching relevant passages: `; документ кодируется без префикса.

Установка в Python-окружении (рекомендуемая версия проекта Python 3.12):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r ml/requirements.txt

# Явная однократная загрузка весов с Hugging Face
python -m ml.download_model --output-dir models/bge-m3-russian-legal

export EMBEDDING_MODEL_PATH="$PWD/models/bge-m3-russian-legal"
export EMBEDDING_DEVICE=cpu

# Сначала применить схему и загрузить подготовленные чанки
python -m alembic upgrade head
python -m ml.index_content --batch-size 8

python -m ml.search --mode embedding --query "авторское право" --limit 5
python -m ml.search --mode hybrid --query "авторское право" --limit 5
```

Вместо `export` путь и устройство можно указать в `.env`. Для воспроизводимой загрузки `ml.download_model` принимает `--revision <commit-hash>`.

Модель загружается один раз на процесс и использует только локальные файлы (`local_files_only=True`, `trust_remote_code=False`). Миграции, старт обычного API и юнит-тесты не скачивают модель. Размерность проверяется до записи в PostgreSQL. Пустые, нулевые и нечисловые/бесконечные векторы отклоняются. Текст длиннее 512 токенов отклоняется вместо молчаливого обрезания; чанки нужно подготовить заранее с учётом tokenizer модели. Автоматическое разбиение документов и оценка качества retrieval пока не реализованы.

`ml.index_content` по умолчанию обрабатывает только чанки без embedding, коммитит небольшими пакетами и не записывает результат поверх одновременно изменённого текста. После смены весов используйте `--force`, чтобы пересчитать весь корпус; при работе с несколькими версиями модели понадобится отдельная версия индекса, которой в исходной схеме нет.

Hybrid-режим объединяет TF-IDF и pgvector cosine search через reciprocal rank fusion. Это исходная реализация поиска фрагментов, качество которой нужно измерять на утверждённой выборке. Она не генерирует юридические ответы и не заменяет юристом подготовленные правила.

## Compose с локальной моделью

После загрузки модели в `./models/bge-m3-russian-legal`:

```sh
docker compose -f docker-compose.yml -f compose.ml.yml up --build -d
docker compose -f docker-compose.yml -f compose.ml.yml exec api python -m ml.index_content
docker compose -f docker-compose.yml -f compose.ml.yml exec api \
  python -m ml.search --mode hybrid --query "авторское право"
```

Overlay устанавливает CPU-версию PyTorch и sentence-transformers, монтирует `./models` только для чтения и задаёт путь модели. Новые сервисы не добавляются. Обычный `docker compose up --build` использует базовые зависимости без PyTorch.

Успешность установки и скорость inference на конкретном VPS зависят от доступной памяти, CPU и размера пакета. Большие веса не хранятся в Git. Сетевого API поиска пока нет: поиск доступен как Python-компоненты и CLI; `/api/v1/analyze` остаётся явно обозначенной заглушкой.
