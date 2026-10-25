# MeLawDy на VPS lawmposer.ru

Развёртывание разрешено отдельно от локального Compose: существующий k3s, namespace `melawdy`, существующие Traefik и cert-manager. Ресурсы ruleshift не изменяются. В кластере дополнительно создаётся отдельный `PriorityClass` `melawdy-low-priority` с приоритетом -1000 и `preemptionPolicy: Never`: MeLawDy уступает ресурсы ранее запущенным приложениям.

Адрес VPS: `193.233.18.123`. DNS A-записи для `@` и `www` должны указывать на этот IP. HTTPS-сертификат `lawmposer-tls` выдаётся существующим `ClusterIssuer/letsencrypt-prod`; HTTP перенаправляется на HTTPS.

## Состав

- `web`: статический интерфейс и Nginx; наружу доступен через Ingress.
- `api`: FastAPI, внутренний Service, одна реплика.
- `postgres`: отдельный PostgreSQL 17 / pgvector, PVC `data-postgres-0`, база `melawdy`, роль `melawdy_app` без SUPERUSER.
- `melawdy-secrets`: отдельные случайные пароли PostgreSQL и администратора; не хранится в Git.

Загрузка файлов ещё не реализована. Workflow явно задаёт `EMBEDDINGS_ENABLED=true` для релизного API-образа; тот же параметр закреплён в манифесте API. Релизный API-образ содержит CPU-модель E5 в `/opt/embedding-model`; перед запуском сервера рассчитываются недостающие embeddings. API требует request 1 GiB / limit 2 GiB, startup-пробе отведено 15 минут. На VPS около 3 ГБ RAM и уже есть другие приложения; перед применением этих лимитов нужно проверить доступные ресурсы. Пониженный приоритет MeLawDy сохраняется.

NetworkPolicy разрешает связи внутри MeLawDy, DNS и вход от Traefik к web. У контейнеров нет токенов ServiceAccount. API работает от непривилегированного пользователя с read-only root filesystem. API и PostgreSQL не публикуются на внешних портах.

## Первый запуск

Команды ниже выполняются на VPS с root-доступом к k3s. Каталог развёртывания — `/opt/melawdy/k3s`.

Образы предварительно собираются локально из текущего кода, получают версионные теги из `kustomization.yaml`, передаются архивом `docker save | gzip` и импортируются в containerd. `imagePullPolicy: Never` требует наличия этих образов именно на узле k3s.

```sh
# images.tar.gz содержит три образа с тегами из kustomization.yaml
gzip -dc /opt/melawdy/images.tar.gz | k3s ctr images import -
k3s kubectl apply -f /opt/melawdy/k3s/namespace.yaml

# secrets.json создаётся отдельно с правами 0600.
# Это Kubernetes Secret melawdy-secrets в namespace melawdy;
# stringData содержит postgres-root-password, postgres-app-password, admin-password.
k3s kubectl apply -f /opt/melawdy/secrets.json
k3s kubectl apply -k /opt/melawdy/k3s
```

Первоначальный email администратора — `admin@lawmposer.ru`; локальная база и локальные учётные записи не переносятся автоматически. API применяет Alembic и создаёт администратора из Secret, сохраняя существующий пароль при последующих стартах. Сгенерированные данные входа сохраняются на компьютере разработчика в `.admin-credentials-vps` (0600, исключён из Git).

11 октября 2026 года существующая учётная запись на VPS переименована в `admin` по запросу владельца; актуальные данные входа находятся в `.admin-credentials-vps`. Манифест теперь рассчитан на эту существующую базу: при перезапуске API сохраняет настроенную учётную запись. Для установки с пустой базой сначала задайте корректный email и пароль длиной от 5 символов для первичного создания администратора. В словарь VPS импортированы 25 уникальных терминов из `deploy/data/glossary-20261011.json`; повтор «Фонограмма / мастер» исключён. Резервная копия до изменения — `/opt/melawdy/backups/20261011-admin-glossary/`.

## Проверка состояния

```sh
k3s kubectl -n melawdy get pods,svc,ingress,pvc
k3s kubectl -n melawdy get certificates
k3s kubectl -n melawdy logs deployment/api --tail=50
```

После выдачи сертификата сайт — `https://lawmposer.ru`, админ-панель — `https://lawmposer.ru/admin.html`. Для корня домена и www используется один сертификат.

## Остановка и включение

```sh
# Отключить сайт и API, оставив PostgreSQL работающей
k3s kubectl -n melawdy scale deployment web api --replicas=0

# Включить обратно
k3s kubectl -n melawdy scale deployment web api --replicas=1

# При необходимости остановить также базу, сохранив PVC
k3s kubectl -n melawdy scale statefulset postgres --replicas=0

# Включить базу
k3s kubectl -n melawdy scale statefulset postgres --replicas=1
```

Не удаляйте namespace или PVC для обычной остановки: local-path по умолчанию удаляет данные вместе с PVC. Данные хранятся на диске одного VPS, репликации на другой сервер нет.

## Автоматическое обновление из main

GitHub хранит исходный код; VPS запускает собранные из него образы API и web. В workflow `.github/workflows/tests.yml` добавлен job `Deploy main to VPS`: при push в `main` он ждёт успешного завершения юнит-тестов и интеграционных проверок PostgreSQL, затем собирает образы с тегом полного SHA проверенного коммита. Изменения в `neuroslop` сами по себе сайт не обновляют: сначала нужно слить ветку в `main`. Ручной запуск workflow Tests на ветке `main` повторяет ту же цепочку с тестами.

Workflow включает `IMPORT_FEES=true`: при запуске API на VPS после миграций выполняется
`python -m backend.import_fees`. JSON из `docs/examples/Выбор_процедуры_Xmind.json`
включён в образ; повторный импорт обновляет дерево и формулы в БД.

После rollout и проверки сайта серверный `deploy-release.sh` запускает в API-контейнере
`python -m backend.import_template /app/docs/examples/coauthors-template.json`.
Шаблон берётся из образа развёрнутого коммита; существующая запись обновляется по slug.
Импорт ограничен 120 секундами, ошибка прерывает деплой и возвращает прежние образы;
данные шаблона автоматически не откатываются. Этот шаг выполняется только на VPS,
при локальном запуске приложения или Docker Compose он не вызывается.

Сборка выполняется на GitHub runner, чтобы не нагружать небольшой VPS. `deploy/k3s/publish-release.sh` передаёт два образа по SSH; установленный на VPS `/usr/local/sbin/melawdy-deploy` из `deploy/k3s/deploy-release.sh` проверяет архив и SHA, импортирует образы в containerd и обновляет только deployments `api` и `web` в namespace `melawdy`. PostgreSQL, Secret, PVC и другие приложения не пересоздаются. Перед деплоем автоматический дамп базы не создаётся; миграции Alembic применяются обычным запуском API.

GitHub Actions использует repository secrets `VPS_SSH_KEY` и `VPS_KNOWN_HOSTS`. Это отдельный ключ с принудительной командой деплоя и запретом SSH forwarding/PTY; SSH-пароль VPS и пароль администратора сайта в GitHub не передаются. Ключ хоста проверяется по значению, полученному через ранее доверенное SSH-подключение. Новый сервер требует отдельной установки скрипта и публичного ключа; изменение скрипта в Git не заменяет установленную на VPS копию автоматически.

Деплой сериализован GitHub concurrency и серверным `flock`. Устаревший запуск пропускается, если его SHA уже не является вершиной `main`. После обновления проверяются readiness обоих deployments, публичный API и `https://lawmposer.ru/version.json`: этот файл содержит `revision` с SHA работающей версии. Успешный SHA также хранится в `/opt/melawdy/deployed-revision` и аннотации deployments `melawdy.ru/revision`; теги в `/opt/melawdy/k3s/kustomization.yaml` обновляются до той же версии.

Перед передачей образы сжимаются в архив; CI выводит его размер. Сервер ожидает загрузку до 900 секунд (15 минут), при этом общий лимит job остаётся 25 минут. Ошибка `124` на этапе загрузки означает превышение серверного таймаута; работающая версия приложения на этом этапе ещё не изменена. Установленная на VPS копия скрипта должна обновляться вместе с изменением этого ограничения в репозитории.

Если rollout или проверка сайта завершается ошибкой, скрипт возвращает прежние образы API и web. Миграции базы автоматически не откатываются, поэтому делайте их совместимыми с предыдущей версией приложения. Дамп базы в автоматическом деплое не создаётся; перед несовместимыми изменениями схемы резервную копию нужно сделать отдельно. Загруженный архив образов удаляется после выполнения.

Web и api обновляются со стратегией `Recreate`: API недоступен до окончания индексации. Изменения инфраструктурных манифестов применяются отдельно оператором; автоматический деплой обновляет код приложения, миграции и недостающие embeddings. Перед первым релизом E5 обновите `/opt/melawdy/k3s/application.yaml`, примените манифесты и обновите серверный `deploy-release.sh`, чтобы ожидание rollout API составляло 900 секунд. Релиз собирается с `DOWNLOAD_EMBEDDING_MODEL=true`, поэтому NetworkPolicy не требует разрешать обращения к Hugging Face.

## Ручное обслуживание

```sh
# Текущая версия и образы
cat /opt/melawdy/deployed-revision
k3s kubectl -n melawdy get deployment api web -o wide
curl --fail https://lawmposer.ru/version.json

```

При ручном применении `k3s kubectl apply -k /opt/melawdy/k3s` используются теги последней успешной версии; replicas возвращаются к 1, включая остановленные ранее компоненты. Состояние GitHub Actions видно на странице Actions репозитория. После ротации ключа нужно заменить соответствующую строку в `/root/.ssh/authorized_keys` и repository secret `VPS_SSH_KEY`.

## Резервная копия

На VPS:

```sh
install -d -m 700 /opt/melawdy/backups
umask 077
k3s kubectl -n melawdy exec postgres-0 -- pg_dump -U postgres -d melawdy -Fc > /opt/melawdy/backups/melawdy-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Регулярное расписание и хранение копий вне VPS нужно настроить отдельно. Разовый dump на том же сервере не защищает от потери VPS.
