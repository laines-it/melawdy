# Поиск по эмбеддингам и TF-IDF

## Модель и ранжирование

Ветка `search-embeddings` использует локальный `SentenceTransformer("alekseevpavel04/multilingual-e5-small-ru-law")`. Hugging Face Inference Endpoint и API-токен не нужны. Модель скачивается при первом расчёте векторов и переиспользуется из дискового кэша; каждый процесс хранит загруженную модель в RAM. Релизный образ для VPS содержит веса и загружает их без сети.

Согласно [карточке модели](https://huggingface.co/alekseevpavel04/multilingual-e5-small-ru-law), векторы имеют 384 измерения, вход ограничен 512 токенами, обязательны префиксы `query: ` для запроса и `passage: ` для документа. Префиксы добавляет `LegalEmbedder`; векторы нормализуются. Длинный документ временно делится по абзацам, предложениям или границе токенового бюджета. Весь текст кодируется, а вектор исходного чанка получается нормализацией среднего по частям с весами по длине. Текст, ID и порядок чанков в БД сохраняются. Усреднение может ослабить отдельные темы большого чанка; слишком длинные запросы по-прежнему отклоняются.

`ml.embedding_search.search_embeddings(query, session=session, limit=10)` кодирует только запрос. PostgreSQL сравнивает его с сохранёнными в `content_item_chunks.embedding` векторами по cosine distance. Каждый материал получает оценку лучшего чанка и возвращается один раз; лимит применяется после выбора лучшего чанка. Учитываются все опубликованные типы материалов с наступившей датой публикации, включая чек-листы.

API `GET /api/v1/public/search?query=...&limit=10` по умолчанию использует embeddings. Формат совпадает с веткой BM25: `{"article_ids": ["2", "3"], "title": "Заголовок первого материала", "summary": "Описание"}`. При отсутствии результатов возвращается `{"article_ids": [], "title": null, "summary": null}`. Для TF-IDF укажите `method=tfidf`. Страница также принимает прежний массив результатов при обновлении контейнеров по отдельности.

## Запуск через Docker Compose

Обычная сборка API устанавливает CPU PyTorch и sentence-transformers. Кэш модели сохраняется в Docker volume `model_cache`.

Из рабочего каталога ветки выполните:

```sh
docker compose up --build -d
```

`backend/entrypoint.sh` выполняет миграции, создаёт администратора из окружения, запускает `python -m ml.index_content` и только затем запускает Uvicorn. Поэтому каждый деплой и перезапуск рассчитывает недостающие embeddings автоматически. Готовые векторы пропускаются; если расчёт не нужен, модель не загружается в процесс индексатора. При ошибке или оставшихся пустых векторах процесс завершается с ненулевым кодом, API не запускается. Логи видны через `docker compose logs -f api`.

Миграция `0007_e5_embeddings` переводит колонку с 1024 на 384 измерения и очищает только несовместимые embeddings; тексты и остальные данные сохраняются. После перехода индексация перед запуском API восстанавливает векторы. Обратная миграция также требует пересчёта для прежней модели.

Первый запуск может занять несколько минут; startup-проверке отведено 15 минут. Индексатор сохраняет результат пакетами, печатает прогресс и проверяет `updated_at` и исходный текст перед записью. После редактирования контента в работающем приложении пересчёт выполняется при следующем старте или вручную:

```sh
docker compose exec api python -m ml.index_content --batch-size 8
```

Для полного пересчёта добавьте `--force`.

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
```

При сборке релизов `deploy/k3s/publish-release.sh` передаёт `DOWNLOAD_EMBEDDING_MODEL=true`: веса включаются в `/opt/embedding-model`. `get_embedder` автоматически выбирает этот каталог с `local_files_only=True`, что подходит для закрытой NetworkPolicy. Перед первым таким релизом обновите манифест API и серверный `deploy-release.sh`: CPU-модели выделены request 1 GiB / limit 2 GiB, startup и ожидание rollout увеличены до 15 минут. Манифесты применяются отдельно оператором, автоматическая смена образа не обновляет лимиты ресурсов.

## TF-IDF и гибридный поиск

`TfidfIndex` использует униграммы/биграммы и cosine similarity. Гибридный CLI объединяет TF-IDF и embeddings через reciprocal rank fusion:

```sh
python -m ml.search --mode tfidf --query "авторское право"
python -m ml.search --mode hybrid --query "авторское право"
```

Юнит-тесты используют искусственные тексты, векторы и mock-модель, без БД и скачивания весов. Качество поиска и пороги cosine similarity следует оценивать на размеченных запросах к вашему корпусу. `/api/v1/analyze` остаётся заглушкой.
