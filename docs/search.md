# Поиск по эмбеддингам и TF-IDF

## Модель и ранжирование

Ветка `search-embeddings` использует локальный `SentenceTransformer("alekseevpavel04/multilingual-e5-small-ru-law")`. Hugging Face Inference Endpoint и API-токен не нужны. При первом обращении модель скачивается с Hugging Face, затем переиспользуется из дискового кэша и загружается один раз на процесс.

Согласно [карточке модели](https://huggingface.co/alekseevpavel04/multilingual-e5-small-ru-law), векторы имеют 384 измерения, вход ограничен 512 токенами, обязательны префиксы `query: ` для запроса и `passage: ` для документа. Префиксы добавляет `LegalEmbedder`; векторы нормализуются. Слишком длинные тексты отклоняются вместо молчаливого обрезания.

`ml.embedding_search.search_embeddings(query, session=session, limit=10)` кодирует только запрос. PostgreSQL сравнивает его с сохранёнными в `content_item_chunks.embedding` векторами по cosine distance. Каждый материал получает оценку лучшего чанка и возвращается один раз; лимит применяется после выбора лучшего чанка. Учитываются все опубликованные типы материалов с наступившей датой публикации, включая чек-листы.

API `GET /api/v1/public/search?query=...&limit=10` по умолчанию использует embeddings. Ответ сохраняет контракт главной: массив объектов `article_id`, `title`, `body`, `score`. `body` — лучший чанк, `score` — cosine similarity, а не вероятность релевантности. Без проиндексированных чанков результат пустой. Для TF-IDF укажите `method=tfidf`.

## Запуск через Docker Compose

Обычная сборка API устанавливает CPU PyTorch и sentence-transformers. Кэш модели сохраняется в Docker volume `model_cache`.

Из рабочего каталога ветки выполните:

```sh
docker compose up --build -d
docker compose exec api python -m ml.index_content --batch-size 8
```

Миграция `0007_e5_embeddings` переводит колонку с 1024 на 384 измерения и очищает только несовместимые embeddings; тексты и остальные данные сохраняются. Поэтому после перехода необходимо заново рассчитать векторы. Обратная миграция также требует пересчёта для прежней модели.

Первый запуск индексации скачивает модель и может занять время. До завершения индексации поиск не готов. Последующие запуски рассчитывают только отсутствующие векторы; для полного пересчёта добавьте `--force`. Запись проверяет `updated_at`, чтобы не сохранить вектор поверх одновременно отредактированного текста.

```sh
docker compose exec api python -m ml.search --mode embedding --query "как зарегистрировать песню" --limit 5
```

CLI возвращает отдельные чанки; публичный API объединяет их в уникальные материалы. Автоматической подмены embeddings на TF-IDF при ошибке нет. Неудачная загрузка модели возвращает 503, слишком длинный запрос — 422.

## Запуск Python без Docker

```sh
python -m pip install -r backend/requirements.txt
python -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r ml/requirements.txt
python -m alembic upgrade head
python -m ml.index_content --batch-size 8
```

PostgreSQL берётся из `.env` или `POSTGRES_*`. По умолчанию модель работает на CPU; устройство задаётся через `EMBEDDING_DEVICE`.

## Работа без сети

Можно заранее скачать модель в отдельный каталог:

```sh
python -m ml.download_model --output-dir models/multilingual-e5-small-ru-law
```

Для воспроизводимости команда принимает `--revision <commit-hash>`. Укажите `EMBEDDING_MODEL_PATH` с путём к скачанному каталогу: тогда SentenceTransformer использует `local_files_only=True`. В Docker каталог подключается так:

```sh
docker compose -f docker-compose.yml -f compose.ml.yml up --build -d
docker compose -f docker-compose.yml -f compose.ml.yml exec api python -m ml.index_content
```

## TF-IDF и гибридный поиск

`TfidfIndex` использует униграммы/биграммы и cosine similarity. Гибридный CLI объединяет TF-IDF и embeddings через reciprocal rank fusion:

```sh
python -m ml.search --mode tfidf --query "авторское право"
python -m ml.search --mode hybrid --query "авторское право"
```

Юнит-тесты используют искусственные тексты, векторы и mock-модель, без БД и скачивания весов. Качество поиска и пороги cosine similarity следует оценивать на размеченных запросах к вашему корпусу. `/api/v1/analyze` остаётся заглушкой.
