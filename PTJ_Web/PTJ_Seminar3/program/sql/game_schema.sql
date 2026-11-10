

CREATE SCHEMA IF NOT EXISTS game;
REVOKE ALL ON SCHEMA game FROM PUBLIC;

CREATE TABLE IF NOT EXISTS game.cases (
    id             TEXT PRIMARY KEY,
    seed           INTEGER NOT NULL,
    level          TEXT NOT NULL CHECK (level IN ('easy', 'medium', 'hard')),
    role_password  TEXT NOT NULL,
    briefing       TEXT NOT NULL,
    answers        JSONB NOT NULL,
    messages       JSONB NOT NULL,   
    hints          JSONB NOT NULL,   
    solved         INTEGER NOT NULL DEFAULT 0,   
    hints_used     INTEGER NOT NULL DEFAULT 0,
    wrong_answers  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ
);
