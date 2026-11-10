-- Police archive tables (a trimmed PostgreSQL port of the SQL Murder Mystery schema).
-- Names are unqualified: the same DDL creates the base `police` schema and
-- every generated `case_<id>` schema (run with search_path set to it).
-- Dates are INTEGER YYYYMMDD, e.g. 20260701 = July 1, 2026.

CREATE TABLE drivers_license (
    id            INTEGER PRIMARY KEY,
    gender        TEXT,
    height        INTEGER,
    hair_color    TEXT,
    plate_number  TEXT,
    car_make      TEXT,
    car_model     TEXT
);

CREATE TABLE person (
    id                   INTEGER PRIMARY KEY,
    name                 TEXT UNIQUE,
    license_id           INTEGER REFERENCES drivers_license(id),
    address_number       INTEGER,
    address_street_name  TEXT
);

CREATE TABLE crime_scene_report (
    date         INTEGER,
    type         TEXT,
    city         TEXT,
    description  TEXT
);

CREATE TABLE interview (
    person_id   INTEGER REFERENCES person(id),
    transcript  TEXT
);

CREATE TABLE facebook_event_checkin (
    person_id   INTEGER REFERENCES person(id),
    event_name  TEXT,
    date        INTEGER
);

CREATE TABLE get_fit_now_member (
    id                 TEXT PRIMARY KEY,
    person_id          INTEGER REFERENCES person(id),
    membership_status  TEXT            -- gold, silver or regular
);

CREATE TABLE get_fit_now_check_in (
    membership_id   TEXT REFERENCES get_fit_now_member(id),
    check_in_date   INTEGER
);
