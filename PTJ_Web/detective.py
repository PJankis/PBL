""" Terminalo programa """
import argparse
import hashlib
import json
import os
import secrets
import sys
import textwrap
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from scenario import LEVELS, build_case, verify_sql

ADMIN_DSN = os.environ.get("ADMIN_DSN", "postgresql://murder_admin:murder_admin@localhost:5432/murder")
TIMEOUT_MS = 3000
ROW_LIMIT = 200
SQL_DIR = Path(__file__).resolve().parent / "sql"
TABLES = ["drivers_license", "person", "get_fit_now_member", "get_fit_now_check_in",
          "social_media_event_checkin", "crime_scene_report", "interview"]   # pirmiau tėvinės lentelės
MAX_HINTS = {"easy": None, "medium": 6, "hard": 4}
BASE_SCORE = {"easy": 100, "medium": 250, "hard": 500}


def admin() -> psycopg.Connection:
    return psycopg.connect(ADMIN_DSN, autocommit=True)


def player_connection(case_id: str, password: str) -> psycopg.Connection:
    """Prisijungimas bylos role"""
    info = conninfo_to_dict(ADMIN_DSN) | {
        "user": f"p_{case_id}", "password": password,
        
        "options": f"-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS}"}
    return psycopg.connect(make_conninfo(**info), autocommit=True)


def answer_hash(case_id: str, name: str) -> str:
    """Saugo tik atsakymų hash'us."""
    return hashlib.sha256(f"{case_id}:{' '.join(name.lower().split())}".encode()).hexdigest()



def cmd_setup(args) -> None:
    with admin() as conn:
        if args.reset:
            drop_cases(conn, "all")
            conn.execute("DROP SCHEMA IF EXISTS police, game CASCADE")
        conn.execute("CREATE SCHEMA police")
        conn.execute("SET search_path TO police")
        conn.execute((SQL_DIR / "tables.sql").read_text(encoding="utf-8"))
        conn.execute((SQL_DIR / "police_data.sql").read_text(encoding="utf-8"))
        conn.execute("SET search_path TO public")
        conn.execute((SQL_DIR / "game_schema.sql").read_text(encoding="utf-8"))
        conn.execute("REVOKE ALL ON SCHEMA police FROM PUBLIC")
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(conn.info.dbname)))
        n = conn.execute("SELECT count(*) FROM police.person").fetchone()[0]
    print(f"police archive loaded: {n} people")


# Nauja byla
class NotUnique(Exception):
    pass


def load_base(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        return {t: cur.execute(f"SELECT * FROM police.{t} ORDER BY 1, 2").fetchall() for t in TABLES}


def provision(conn, case, case_id: str, seed: int, level: str) -> None:
   
    S, R = sql.Identifier(f"case_{case_id}"), sql.Identifier(f"p_{case_id}")
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(S))
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(S))
    conn.execute((SQL_DIR / "tables.sql").read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for table in TABLES:
            cols = list(case.tables[table][0])
            with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols)))) as copy:
                for row in case.tables[table]:
                    copy.write_row([row[c] for c in cols])
        failed = verify_sql(cur, case.checks)
    if failed:
        raise NotUnique(failed)

    
    password = secrets.token_urlsafe(18)
    conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT CONNECTION LIMIT 3 PASSWORD {}")
                 .format(R, sql.Literal(password)))
    conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(R))
    conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(R, sql.Literal(f"{TIMEOUT_MS}ms")))
    conn.execute(sql.SQL("ALTER ROLE {} SET search_path = {}").format(R, S))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(conn.info.dbname), R))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(S, R))
    conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(S, R))

    hints = case.hints[:MAX_HINTS[level]]
    answers = [{"stage": s, "hash": answer_hash(case_id, name)} for s, name in case.solution.items()]
    conn.execute("""INSERT INTO game.cases (id, seed, level, role_password, briefing, answers, messages, hints)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                 (case_id, seed, level, password, case.briefing, json.dumps(answers),
                  json.dumps(case.messages), json.dumps(hints)))


def generate(conn, base, seed: int, level: str, case_id: str, keep: bool = True):
   
    for attempt in range(20):
        case = build_case(base, seed, attempt, level)
        try:
            with conn.transaction() as tx:
                provision(conn, case, case_id, seed, level)
                if not keep:
                    raise psycopg.Rollback(tx)   # patikrina
            return case, attempt
        except NotUnique:
            continue                             # bando iš naujo
    raise RuntimeError(f"no consistent case for seed {seed}")


def cmd_new(args) -> None:
    seed = args.seed if args.seed is not None else secrets.randbelow(10**6)
    case_id = secrets.token_hex(4)
    started = time.perf_counter()
    with admin() as conn:
        case, attempt = generate(conn, load_base(conn), seed, args.level, case_id)
    ms = (time.perf_counter() - started) * 1000
    print(f"case {case_id}  level={args.level}  seed={seed}  attempt={attempt}  ({ms:.0f} ms)")
    print(f"schema case_{case_id}, role p_{case_id} (read-only, {TIMEOUT_MS} ms limit)\n")
    print(case.briefing + "\n")
    print(f"play:  python detective.py play {case_id}")



def print_table(columns, rows) -> None:
   
    cells = [[textwrap.wrap("" if v is None else str(v), 60) or [""] for v in row] for row in rows]
    widths = [max([len(c)] + [len(x) for r in cells for x in r[i]]) for i, c in enumerate(columns)]
    print(" " + " | ".join(c.ljust(w) for c, w in zip(columns, widths)).rstrip())
    print("+".join("-" * (w + 2) for w in widths))
    for r in cells:
        for k in range(max(len(v) for v in r)):
            print(" " + " | ".join((v[k] if k < len(v) else "").ljust(w) for v, w in zip(r, widths)).rstrip())
    print(f"({len(rows)} row{'' if len(rows) == 1 else 's'})")


def run_query(player, text: str) -> None:
    query = text.strip().rstrip(";").strip()
    if query.split(None, 1)[0].lower() not in ("select", "with"):
        print("rejected: only SELECT queries are allowed")
        return
 
    wrapped = f"SELECT * FROM (\n{query}\n) AS player_query LIMIT {ROW_LIMIT}"
    try:
        cur = player.execute(wrapped, prepare=True)
        print_table([d.name for d in cur.description], cur.fetchall())
    except psycopg.Error as e:
        print(f"ERROR: {e.diag.message_primary or e}")


def load_case(conn, case_id: str, lock: bool = False) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        case = cur.execute("SELECT * FROM game.cases WHERE id = %s" + (" FOR UPDATE" if lock else ""),
                           (case_id,)).fetchone()
    if case is None:
        sys.exit(f"no case {case_id}")
    return case


def take_hint(case_id: str) -> None:
    with admin() as conn, conn.transaction():
        case = load_case(conn, case_id, lock=True)
        n = case["hints_used"]
        if n >= len(case["hints"]):
            print("no hints left for this level")
            return
        conn.execute("UPDATE game.cases SET hints_used = hints_used + 1 WHERE id = %s", (case_id,))
        print(f"hint {n + 1}/{len(case['hints'])}: {case['hints'][n]}")


def accuse(case_id: str, name: str) -> bool:
    
    with admin() as conn, conn.transaction():
        case = load_case(conn, case_id, lock=True)
        stage = case["answers"][case["solved"]]
        if answer_hash(case_id, name) != stage["hash"]:
            conn.execute("UPDATE game.cases SET wrong_answers = wrong_answers + 1 WHERE id = %s", (case_id,))
            print(f"wrong {stage['stage']}. Keep digging.")
            return False
        print(case["messages"][stage["stage"]])
        if case["solved"] + 1 < len(case["answers"]):
            conn.execute("UPDATE game.cases SET solved = solved + 1 WHERE id = %s", (case_id,))
            return False
        conn.execute("UPDATE game.cases SET solved = solved + 1, finished_at = now() WHERE id = %s", (case_id,))
        score = max(BASE_SCORE[case["level"]] // 10,
                    BASE_SCORE[case["level"]] - 20 * case["hints_used"] - 25 * case["wrong_answers"])
        print(f"case closed: score {score} (hints {case['hints_used']}, wrong answers {case['wrong_answers']})")
        return True


HELP = "SQL ends with ';'.  Commands: tables, brief, hint, accuse <name>, quit"


def cmd_play(args) -> None:
    with admin() as conn:
        case = load_case(conn, args.case_id)
    if case["finished_at"]:
        sys.exit("case already closed")
    player = player_connection(args.case_id, case["role_password"])
    print(f"case {args.case_id} [{case['level']}], connected as p_{args.case_id}\n")
    print(case["briefing"] + "\n" + HELP)
    buf: list = []
    while True:
        try:
            line = input("detective> " if not buf else "        -> ")
        except EOFError:
            break
        if not sys.stdin.isatty():   # demo iš failo: parodome įvestį
            print(line)
        word, _, rest = line.strip().lstrip("/\\").partition(" ")
        word, rest = word.lower(), rest.strip()
        if word in ("tables", "brief", "hint", "accuse", "quit", "help"):   # komandos veikia bet kada
            buf = []
            if word == "quit":
                break
            elif word == "tables":
                run_query(player, "SELECT table_name, string_agg(column_name, ', ' ORDER BY ordinal_position) "
                                  "AS columns FROM information_schema.columns "
                                  "WHERE table_schema = current_schema() GROUP BY table_name ORDER BY 1")
            elif word == "brief":
                print(case["briefing"])
            elif word == "hint":
                take_hint(args.case_id)
            elif word == "accuse" and rest:
                if accuse(args.case_id, rest):
                    break
            else:
                print(HELP)
        elif line.strip():
            buf.append(line)
            if line.strip().endswith(";"):
                run_query(player, "\n".join(buf))
                buf = []
    player.close()



def cmd_list(args) -> None:
    with admin() as conn:
        rows = conn.execute("""SELECT id, level, seed, to_char(created_at, 'YYYY-MM-DD HH24:MI'),
                                      CASE WHEN finished_at IS NULL THEN 'open' ELSE 'closed' END
                               FROM game.cases ORDER BY created_at""").fetchall()
    print_table(["case", "level", "seed", "created", "status"], rows)


def drop_cases(conn, which: str) -> int:
    if not conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'game'").fetchone():
        return 0
    ids = [r[0] for r in conn.execute("SELECT id FROM game.cases WHERE %s IN (id, 'all')", (which,))]
    for case_id in ids:
        role = f"p_{case_id}"
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = %s", (role,))
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(f"case_{case_id}")))
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                sql.Identifier(conn.info.dbname), sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        conn.execute("DELETE FROM game.cases WHERE id = %s", (case_id,))
    return len(ids)


def cmd_drop(args) -> None:
    with admin() as conn:
        print(f"dropped {drop_cases(conn, args.case_id)} case(s)")


def cmd_selftest(args) -> None:
    """Tas pats seed'as turi visada duoti tapačią bylą"""
    with admin() as conn:
        base = load_base(conn)
        for level in LEVELS:
            retries, started = 0, time.perf_counter()
            for seed in range(args.count):
                case, attempt = generate(conn, base, seed, level, f"t{seed}", keep=False)
                again = build_case(base, seed, attempt, level)
                assert again.tables == case.tables and again.solution == case.solution, f"seed {seed} differs"
                retries += attempt
            ms = (time.perf_counter() - started) * 1000 / args.count
            print(f"{level:6}  {args.count} seeds: one answer per stage, same case every time, "
                  f"{retries} retries, {ms:.0f} ms/case")


def main() -> None:
    ap = argparse.ArgumentParser(description="Dynamic murder database")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").add_argument("--reset", action="store_true", help="delete everything and reload")
    p = sub.add_parser("new")
    p.add_argument("level", nargs="?", choices=list(LEVELS), default="medium")
    p.add_argument("--seed", type=int)
    sub.add_parser("play").add_argument("case_id")
    sub.add_parser("list")
    sub.add_parser("drop").add_argument("case_id", help="case id or 'all'")
    sub.add_parser("selftest").add_argument("--count", type=int, default=20)
    args = ap.parse_args()
    {"setup": cmd_setup, "new": cmd_new, "play": cmd_play, "list": cmd_list,
     "drop": cmd_drop, "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    main()
