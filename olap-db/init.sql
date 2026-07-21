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

INSERT INTO emg_sensor_data
    (username, prosthesis_type, muscle_group, signal_frequency, signal_amplitude, signal_duration, signal_time)
SELECT username, prosthesis_type, muscle_group, signal_frequency, signal_amplitude, signal_duration, signal_time
FROM file(
    'emg.csv',
    'CSVWithNames',
    'username String, prosthesis_type String, muscle_group String, signal_frequency UInt32, signal_amplitude Decimal(5,2), signal_duration UInt32, signal_time DateTime'
);

CREATE TABLE IF NOT EXISTS report_user_telemetry (
    username             String,
    full_name            String,
    email                String,
    country              String,
    signals_total        UInt64,
    prosthesis_types     UInt64,
    avg_signal_amplitude Nullable(Decimal(10,4)),
    avg_signal_duration  Nullable(Float64),
    period_start         Nullable(DateTime),
    period_end           Nullable(DateTime)
) ENGINE = ReplacingMergeTree()
ORDER BY username;
