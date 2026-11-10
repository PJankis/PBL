-- Policijos archyvo lentelės (sutrumpinta SQL Murder Mystery schema).
-- Be schemos pavadinimų: tas pats failas kuria `police` ir kiekvieną `case_<id>`.
-- Datos INTEGER YYYYMMDD (20260701), laikas INTEGER HHMM (2130 = 21:30).

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

CREATE TABLE social_media_event_checkin (
    person_id      INTEGER REFERENCES person(id),
    event_name     TEXT,
    date           INTEGER,
    check_in_time  INTEGER
);

CREATE TABLE get_fit_now_member (
    id                 TEXT PRIMARY KEY,
    person_id          INTEGER REFERENCES person(id),
    membership_status  TEXT            -- gold, silver arba regular
);

CREATE TABLE get_fit_now_check_in (
    membership_id   TEXT REFERENCES get_fit_now_member(id),
    check_in_date   INTEGER,
    check_in_time   INTEGER,
    check_out_time  INTEGER
);
