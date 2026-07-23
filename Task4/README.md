# Задание 4. CDC для разгрузки CRM (Debezium -> Kafka -> ClickHouse)

Диаграмма: [BionicPRO_cdc_architecture.drawio](./BionicPRO_cdc_architecture.drawio).

## Проблема

Массовые выгрузки из CRM конкурировали с OLTP-запросами и роняли их. Батч-чтение из CRM убрано: изменения переносятся потоково через CDC, транзакционная нагрузка на CRM не растёт.

## Поток данных

```
CRM (Postgres, wal_level=logical)
   -> Debezium (Kafka Connect)  CDC по public.customers
   -> Kafka topic bionicpro_crm.public.customers
   -> ClickHouse Kafka engine (kafka_crm_customers)
   -> MaterializedView mv_crm_customers -> crm_customers_cdc (ReplacingMergeTree)
   -> витрина report_user_telemetry_cdc (join CRM + агрегаты телеметрии)
   -> API /reports
```

## Что сделано

1. **CDC на CRM.** Postgres запущен с `wal_level=logical`, у `customers` выставлен `REPLICA IDENTITY FULL`. Debezium-коннектор ([debezium/crm-connector.json](../debezium/crm-connector.json)) снимает изменения через `pgoutput`.
2. **Kafka.** Debezium публикует события в топик `bionicpro_crm.public.customers`.
3. **KafkaEngine в ClickHouse.** Таблица `kafka_crm_customers` (`ENGINE = Kafka`, формат `JSONAsString`) читает топик.
4. **MaterializedView.** `mv_crm_customers` разбирает Debezium-конверт (`op`, `before`/`after`) и пишет в `crm_customers_cdc` (`ReplacingMergeTree(cdc_version)`), учитывая удаления (`is_deleted`).
5. **Витрина.** Телеметрия агрегируется в разрезе пользователя через MV `mv_telemetry_agg` (`AggregatingMergeTree`). Витрина `report_user_telemetry_cdc` соединяет актуальный срез CRM (`FINAL`, `is_deleted = 0`) с агрегатами телеметрии.
6. **API переведён на новую витрину.** Таблица берётся из `REPORT_TABLE` (по умолчанию `report_user_telemetry_cdc`), см. [backend/app/database.py](../backend/app/database.py).

Airflow больше не читает CRM массово.

## Инвалидация кеша по CDC-событию (по правке ревью)

Раньше кеш S3 чистился только по расписанию Airflow (раз в час), из-за чего пользователь мог получить старый отчёт. Теперь инвалидация привязана к CDC-событию:

- Сервис [cache-invalidator/consumer.py](../cache-invalidator/consumer.py) слушает тот же топик `bionicpro_crm.public.customers`.
- На каждое изменение (`INSERT`/`UPDATE`/`DELETE`) он берёт `username` из события и удаляет `reports/{username}.json` из S3.
- Следующий запрос `/reports` пересобирает отчёт из живой витрины `report_user_telemetry_cdc`.

Так стейл-отчёт исчезает в секунды после изменения в CRM, без ожидания часового DAG. Airflow-DAG [reports_cache_invalidation.py](../airflow/dags/reports_cache_invalidation.py) оставлен только как редкий страховочный полный сброс.

## Проверка

```bash
docker compose up --build
```

- Kafka Connect: http://localhost:8083/connectors (коннектор `bionicpro-crm-postgres-connector`)
- CDC end-to-end: `INSERT`/`UPDATE` в `crm_db.customers` попадает в `crm_customers_cdc` и меняет отчёт без запросов к CRM.
- API `/reports` отдаёт данные из `report_user_telemetry_cdc`.
