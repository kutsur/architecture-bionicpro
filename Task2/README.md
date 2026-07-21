# Задание 2. Сервис отчётов

Диаграмма архитектуры: [BionicPRO_reports_architecture.drawio](./BionicPRO_reports_architecture.drawio).

## Архитектура (подзадача 1)

```
CRM DB (Postgres)  ─┐
                    ├─►  Airflow ETL (по расписанию)  ─►  OLAP витрина (ClickHouse)  ─►  Report Service /reports  ─►  reports-frontend
DB телеметрия (CH) ─┘                                     report_user_telemetry            (RBAC по токену)             (кнопка)
```

- **Источники:** профили клиентов в CRM (PostgreSQL) и телеметрия датчиков (`emg_sensor_data` в ClickHouse).
- **ETL (Airflow):** DAG `crm_to_olap_reporting` по расписанию `0 * * * *` тянет клиентов из CRM, агрегирует телеметрию в разрезе пользователя и строит витрину `report_user_telemetry` в OLAP.
- **OLAP (ClickHouse):** готовая витрина, `ORDER BY username` даёт быстрый доступ по пользователю без вычислений в реальном времени.
- **API (FastAPI):** `GET /reports` возвращает готовый отчёт только для владельца токена.
- **UI (React):** кнопка «Получить отчёт».

## Компоненты в репозитории

| Путь | Что это |
|------|---------|
| [crm-db/](../crm-db/) | CRM-источник: `init.sql` + `crm.csv` (профили клиентов) |
| [olap-db/](../olap-db/) | ClickHouse: `init.sql` (телеметрия + пустая витрина) + `emg.csv` |
| [airflow/dags/crm_to_olap_reporting.py](../airflow/dags/crm_to_olap_reporting.py) | ETL DAG (подзадача 2) |
| [backend/](../backend/) | FastAPI `/reports` + проверка JWT + RBAC (подзадачи 3, 4) |
| [frontend/src/components/ReportPage.tsx](../frontend/src/components/ReportPage.tsx) | Кнопка и отображение отчёта (подзадача 5) |

## Витрина `report_user_telemetry`

Одна строка на пользователя (быстрый доступ по `username`):
`username, full_name, email, country, signals_total, prosthesis_types, avg_signal_amplitude, avg_signal_duration, period_start, period_end`.

## RBAC (подзадача 4)

`/reports` берёт `preferred_username` из проверенного JWT и фильтрует витрину по нему.
Запросить чужой отчёт нельзя: идентификатор пользователя не передаётся клиентом, а извлекается из токена.
- нет токена / невалидный → `401`;
- валидный → только собственная строка витрины.

## Период, ещё не обработанный Airflow

API читает только витрину. Пока Airflow не построил данные (или у пользователя нет телеметрии),
`/reports` возвращает `status: no_data` с сообщением, а не «сырые» или будущие данные.

## Запуск и проверка

```bash
docker compose up --build
```

- Frontend: http://localhost:3000 (войти, нажать «Получить отчёт»)
- Backend: http://localhost:8000/reports (нужен `Authorization: Bearer <token>`)
- Airflow: http://localhost:8088 (admin/admin), DAG `crm_to_olap_reporting`
- ClickHouse: http://localhost:8123

Тестовые пользователи Keycloak: `prothetic1..3`, `user1`, `user2` (для них засеяны данные).
Первый прогон DAG можно запустить вручную в Airflow, дальше он идёт по расписанию.
