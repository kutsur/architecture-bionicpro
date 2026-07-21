CREATE TABLE IF NOT EXISTS customers (
    username    VARCHAR(50) PRIMARY KEY,
    full_name   VARCHAR(150),
    email       VARCHAR(150),
    birth_date  DATE,
    gender      VARCHAR(10),
    country     VARCHAR(100)
);

COPY customers(username, full_name, email, birth_date, gender, country)
FROM '/docker-entrypoint-initdb.d/crm.csv'
DELIMITER ','
CSV HEADER;

ALTER TABLE customers REPLICA IDENTITY FULL;
