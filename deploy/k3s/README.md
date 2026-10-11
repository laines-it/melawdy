# MeLawDy на VPS lawmposer.ru

Развёртывание разрешено отдельно от локального Compose: существующий k3s, namespace `melawdy`, существующие Traefik и cert-manager. Ресурсы ruleshift не изменяются. В кластере дополнительно создаётся отдельный `PriorityClass` `melawdy-low-priority` с приоритетом -1000 и `preemptionPolicy: Never`: MeLawDy уступает ресурсы ранее запущенным приложениям.

Адрес VPS: `193.233.18.123`. DNS A-записи для `@` и `www` должны указывать на этот IP. HTTPS-сертификат `lawmposer-tls` выдаётся существующим `ClusterIssuer/letsencrypt-prod`; HTTP перенаправляется на HTTPS.

## Состав

- `web`: статический интерфейс и Nginx; наружу доступен через Ingress.
- `api`: FastAPI, внутренний Service, одна реплика.
- `postgres`: отдельный PostgreSQL 17 / pgvector, PVC `data-postgres-0`, база `melawdy`, роль `melawdy_app` без SUPERUSER.
- `melawdy-secrets`: отдельные случайные пароли PostgreSQL и администратора; не хранится в Git.

Текущему сайту MinIO не требуется: загрузка файлов ещё не реализована. Он остаётся в локальном Compose. ML-модель на VPS этим развёртыванием не устанавливается. На VPS около 3 ГБ RAM и уже есть другие приложения; заданы небольшие requests, limits и пониженный приоритет. Для дальнейшей нагрузки или локальных embeddings нужно увеличить ресурсы VPS.

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

11 октября 2026 года существующая учётная запись на VPS переименована в `admin` по запросу владельца; актуальные данные входа находятся в `.admin-credentials-vps`. Манифест теперь рассчитан на эту существующую базу: при перезапуске API сохраняет настроенную учётную запись. Для установки с пустой базой сначала задайте корректный email и пароль длиной от 12 символов для первичного создания администратора. В словарь VPS импортированы 25 уникальных терминов из `deploy/data/glossary-20261011.json`; повтор «Фонограмма / мастер» исключён. Резервная копия до изменения — `/opt/melawdy/backups/20261011-admin-glossary/`.

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

## Обновление

1. Соберите новые образы web/api с новым тегом; обновите теги в `kustomization.yaml`.
2. Передайте архив на VPS и импортируйте его в k3s containerd.
3. Сохраните резервную копию базы.
4. Выполните `k3s kubectl apply -k /opt/melawdy/k3s` и проверьте статус.

Для экономии памяти web и api обновляются со стратегией `Recreate`: во время обновления возможен короткий перерыв. Применение манифестов возвращает replicas к 1, включая остановленные ранее компоненты.

## Резервная копия

На VPS:

```sh
install -d -m 700 /opt/melawdy/backups
umask 077
k3s kubectl -n melawdy exec postgres-0 -- pg_dump -U postgres -d melawdy -Fc > /opt/melawdy/backups/melawdy-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Регулярное расписание и хранение копий вне VPS нужно настроить отдельно. Разовый dump на том же сервере не защищает от потери VPS.
