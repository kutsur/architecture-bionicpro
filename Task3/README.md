# Задание 3. Снижение нагрузки на OLAP: S3 + CDN

Диаграмма: [BionicPRO_reports_cdn.drawio](./BionicPRO_reports_cdn.drawio).

## Идея

Между запусками ETL данные не меняются, поэтому отчёт пользователя одинаков.
Сформированный отчёт кешируется в объектном хранилище (MinIO, S3 API) и раздаётся через CDN (Nginx),
чтобы повторные запросы не били по OLAP.

## Поток запроса `GET /reports`

```
1. Проверить наличие reports/{username}.json в S3 (head_object).
2. Есть  -> вернуть ссылку на CDN (обращения к OLAP нет).
3. Нет   -> прочитать строку из витрины OLAP, положить JSON в S3, вернуть ссылку на CDN.
```

Фронтенд получает от API ссылку на CDN и уже с неё скачивает отчёт.

## Структура хранения в S3

- Бакет: `bionicpro-reports`
- Ключ: `reports/{username}.json`

Плоский ключ по `username` даёт быстрый доступ (один HEAD/GET по известному пути) и удобную инвалидацию по префиксу `reports/`.

## Механизм обновления кеша

Кеш инвалидируется ровно в момент обновления данных:

- **S3:** финальная задача DAG `invalidate_cached_reports` после пересборки витрины удаляет все объекты под `reports/`. Следующий запрос пользователя пересоздаёт отчёт из свежей витрины.
- **CDN:** Nginx кеширует ответ коротко (`proxy_cache_valid 200 1m`), поэтому после инвалидации S3 отдаёт свежий объект в пределах TTL. На объект также ставится `Cache-Control: public, max-age=60`.

Итог: обращение к OLAP происходит не чаще, чем один раз на пользователя за цикл ETL; всё остальное отдаётся из S3/CDN.

## CDN (эмуляция)

Nginx как reverse proxy к MinIO с включённым кешированием ([cdn/nginx.conf](../cdn/nginx.conf)).
Заголовок `X-Cache-Status` показывает попадание в кеш (`HIT`/`MISS`).

## Безопасность доступа (по правке ревью)

Бакет закрыт: `mc anonymous set none` (публичного чтения нет).
API отдаёт не прямую ссылку, а **presigned URL** (подписанная, с TTL `REPORT_LINK_TTL`, по умолчанию 120с), сгенерированную под конкретный объект пользователя.
Ссылка ведёт через CDN, который прозрачно проксирует подписанный запрос в MinIO (сохраняя `Host` и query, чтобы подпись SigV4 проверялась).
Без валидной подписи запрос к отчёту возвращает `403`, поэтому ПДн (ФИО, email, телеметрия) больше не доступны анонимно.

## Компоненты

| Путь | Что это |
|------|---------|
| [backend/app/storage.py](../backend/app/storage.py) | Работа с S3 (boto3): exists / put / cdn_url |
| [backend/app/main.py](../backend/app/main.py) | Поток `/reports`: S3 -> CDN или OLAP -> S3 -> CDN |
| [cdn/nginx.conf](../cdn/nginx.conf) | CDN reverse proxy с кешем |
| [airflow/dags/crm_to_olap_reporting.py](../airflow/dags/crm_to_olap_reporting.py) | задача `invalidate_cached_reports` |
| docker-compose | сервисы `minio`, `minio_init`, `cdn` |

## Проверка

```bash
docker compose up --build
```

- MinIO console: http://localhost:9001 (minioadmin/minioadmin)
- CDN: http://localhost:8090/reports-cache/reports/prothetic1.json
- Первый запрос отчёта: `source: olap`; повторный: `source: s3`, заголовок CDN `X-Cache-Status: HIT`.
