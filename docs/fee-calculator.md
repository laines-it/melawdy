# Калькулятор пошлин

Исходное дерево: `docs/examples/Выбор_процедуры_Xmind.json`. Импорт сохраняет его в
`fee_catalogs.source_json` (JSONB) и добавляет процедуры в `application_types`.
Повторный импорт обновляет справочник; сохранённые расчёты сохраняют свои параметры и суммы.

```sh
python -m backend.import_fees
python -m backend.import_fees path/to/tree.json
```

Web получает дерево через `GET /api/v1/public/fees/tree`. Расчёт выполняется на сервере
через `POST /api/v1/public/fees/tree/calculate`, сохранение для авторизованного пользователя —
`POST /api/v1/public/fees/tree/calculations`.

Workflow деплоя передаёт `IMPORT_FEES=true` в образ API. На VPS entrypoint запускает
импорт после `alembic upgrade head`, до старта API. Отдельное обновление установленного
SSH-скрипта деплоя не требуется. При перезапуске API импорт повторяется.

Ставки и формулы используются как в исходном JSON. Для суммы иска выше последнего
описанного диапазона расчёт недоступен. Услуги с диапазоном стоимости отображаются и
сохраняются с нижней и верхней границей.
