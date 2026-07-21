CREATE TABLE IF NOT EXISTS emg_sensor_data (
    username         String,
    prosthesis_type  String,
    muscle_group     String,
    signal_frequency UInt32,
    signal_amplitude Decimal(5,2),
    signal_duration  UInt32,
    signal_time      DateTime
) ENGINE = MergeTree()
ORDER BY (username, signal_time);

CREATE TABLE IF NOT EXISTS telemetry_agg (
    username String,
    cnt    AggregateFunction(count),
    ptypes AggregateFunction(uniqExact, String),
    amp    AggregateFunction(avg, Decimal(5,2)),
    dur    AggregateFunction(avg, UInt32),
    pstart AggregateFunction(min, DateTime),
    pend   AggregateFunction(max, DateTime)
) ENGINE = AggregatingMergeTree()
ORDER BY username;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_telemetry_agg TO telemetry_agg AS
SELECT
    username,
    countState()                     AS cnt,
    uniqExactState(prosthesis_type)  AS ptypes,
    avgState(signal_amplitude)       AS amp,
    avgState(signal_duration)        AS dur,
    minState(signal_time)            AS pstart,
    maxState(signal_time)            AS pend
FROM emg_sensor_data
GROUP BY username;

INSERT INTO emg_sensor_data
    (username, prosthesis_type, muscle_group, signal_frequency, signal_amplitude, signal_duration, signal_time)
SELECT username, prosthesis_type, muscle_group, signal_frequency, signal_amplitude, signal_duration, signal_time
FROM file(
    'emg.csv',
    'CSVWithNames',
    'username String, prosthesis_type String, muscle_group String, signal_frequency UInt32, signal_amplitude Decimal(5,2), signal_duration UInt32, signal_time DateTime'
);

CREATE TABLE IF NOT EXISTS kafka_crm_customers (
    message String
) ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'bionicpro_crm.public.customers',
    kafka_group_name = 'clickhouse_crm_customers',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 1,
    kafka_skip_broken_messages = 1000;

CREATE TABLE IF NOT EXISTS crm_customers_cdc (
    username    String,
    full_name   String,
    email       String,
    birth_date  Date,
    gender      String,
    country     String,
    cdc_op      LowCardinality(String),
    is_deleted  UInt8,
    cdc_version UInt64
) ENGINE = ReplacingMergeTree(cdc_version)
ORDER BY username;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_crm_customers TO crm_customers_cdc AS
WITH
    JSONExtractString(message, 'op') AS op,
    if(op = 'd', JSONExtractRaw(message, 'before'), JSONExtractRaw(message, 'after')) AS row
SELECT
    JSONExtractString(row, 'username')                                AS username,
    JSONExtractString(row, 'full_name')                               AS full_name,
    JSONExtractString(row, 'email')                                   AS email,
    toDate('1970-01-01') + toInt32(JSONExtractInt(row, 'birth_date')) AS birth_date,
    JSONExtractString(row, 'gender')                                  AS gender,
    JSONExtractString(row, 'country')                                 AS country,
    op                                                                AS cdc_op,
    if(op = 'd', 1, 0)                                                AS is_deleted,
    if(JSONExtractUInt(message, 'ts_ms') = 0,
       toUInt64(toUnixTimestamp64Milli(now64(3))),
       JSONExtractUInt(message, 'ts_ms'))                             AS cdc_version
FROM kafka_crm_customers
WHERE row != '' AND JSONExtractString(row, 'username') != '';

CREATE VIEW IF NOT EXISTS report_user_telemetry_cdc AS
SELECT
    c.username                        AS username,
    c.full_name                       AS full_name,
    c.email                           AS email,
    c.country                         AS country,
    toUInt64(countMerge(t.cnt))       AS signals_total,
    toUInt64(uniqExactMerge(t.ptypes)) AS prosthesis_types,
    round(avgMerge(t.amp), 4)         AS avg_signal_amplitude,
    round(avgMerge(t.dur), 2)         AS avg_signal_duration,
    minMerge(t.pstart)                AS period_start,
    maxMerge(t.pend)                  AS period_end
FROM telemetry_agg AS t
INNER JOIN
(
    SELECT * FROM crm_customers_cdc FINAL WHERE is_deleted = 0
) AS c ON c.username = t.username
GROUP BY c.username, c.full_name, c.email, c.country;
