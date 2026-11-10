"""Web"""
import argparse
import json
import re
import secrets
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg

from detective import (BASE_SCORE, ROW_LIMIT, admin, answer_hash, generate, load_base,
                       player_connection)
from scenario import LEVELS

STATIC = Path(__file__).resolve().parent / "static"
CASE_ID = re.compile(r"^[0-9a-f]{8}$")
MAX_BODY = 20_000


class GameError(Exception):
    """Error'o message"""


def get_case(conn, case_id, lock=False):
    if not CASE_ID.match(case_id or ""):
        raise GameError("bad case id")
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        case = cur.execute("SELECT * FROM game.cases WHERE id = %s" + (" FOR UPDATE" if lock else ""),
                           (case_id,)).fetchone()
    if case is None:
        raise GameError(f"no case {case_id}")
    return case


def public_state(case):
    return {"id": case["id"], "level": case["level"], "seed": case["seed"], "briefing": case["briefing"],
            "stages": [a["stage"] for a in case["answers"]], "solved": case["solved"],
            "hints_used": case["hints_used"], "hints_total": len(case["hints"]),
            "wrong_answers": case["wrong_answers"], "closed": case["finished_at"] is not None}



def new_case(body):
    level = body.get("level", "medium")
    if level not in LEVELS:
        raise GameError("level must be easy, medium or hard")
    seed = body.get("seed")
    seed = int(seed) if seed not in (None, "") else secrets.randbelow(10**6)
    case_id = secrets.token_hex(4)
    with admin() as conn:
        generate(conn, load_base(conn), seed, level, case_id)
        return public_state(get_case(conn, case_id))


def case_state(case_id):
    with admin() as conn:
        return public_state(get_case(conn, case_id))


def run_query(body):
    with admin() as conn:
        case = get_case(conn, body.get("id"))
    query = str(body.get("sql", "")).strip().rstrip(";").strip()
    if not query or query.split(None, 1)[0].lower() not in ("select", "with"):
        raise GameError("only SELECT queries are allowed")
    # Apsauga kaip detective.py: subužklausa + LIMIT, prepare, žaidėjo rolė.
    wrapped = f"SELECT * FROM (\n{query}\n) AS player_query LIMIT {ROW_LIMIT}"
    with player_connection(case["id"], case["role_password"]) as player:
        try:
            cur = player.execute(wrapped, prepare=True)
        except psycopg.Error as e:
            raise GameError(e.diag.message_primary or str(e))
        columns = [d.name for d in cur.description]
        rows = [[v if isinstance(v, (int, float, str)) or v is None else str(v) for v in r] for r in cur.fetchall()]
    return {"columns": columns, "rows": rows, "limited": len(rows) == ROW_LIMIT}


def take_hint(body):
    with admin() as conn, conn.transaction():
        case = get_case(conn, body.get("id"), lock=True)
        if case["finished_at"]:
            raise GameError("this case is already closed")
        n = case["hints_used"]
        if n >= len(case["hints"]):
            return {"message": "No hints left for this level."}
        conn.execute("UPDATE game.cases SET hints_used = hints_used + 1 WHERE id = %s", (case["id"],))
        return {"message": f"Hint {n + 1}/{len(case['hints'])}: {case['hints'][n]}"}


def accuse(body):
    name = str(body.get("name", "")).strip()
    if not name:
        raise GameError("type a name first")
    with admin() as conn, conn.transaction():
        case = get_case(conn, body.get("id"), lock=True)
        if case["finished_at"]:
            raise GameError("this case is already closed")
        stage = case["answers"][case["solved"]]
        if answer_hash(case["id"], name) != stage["hash"]:
            conn.execute("UPDATE game.cases SET wrong_answers = wrong_answers + 1 WHERE id = %s", (case["id"],))
            return {"correct": False, "message": f"Wrong {stage['stage']}. Keep digging."}
        message = case["messages"][stage["stage"]]
        if case["solved"] + 1 < len(case["answers"]):
            conn.execute("UPDATE game.cases SET solved = solved + 1 WHERE id = %s", (case["id"],))
            return {"correct": True, "closed": False, "message": message}
        conn.execute("UPDATE game.cases SET solved = solved + 1, finished_at = now() WHERE id = %s", (case["id"],))
        base = BASE_SCORE[case["level"]]
        score = max(base // 10, base - 20 * case["hints_used"] - 25 * case["wrong_answers"])
        return {"correct": True, "closed": True,
                "message": f"{message} Case closed. Score: {score} "
                           f"(hints {case['hints_used']}, wrong answers {case['wrong_answers']})."}



class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, default=lambda v: v.isoformat() if isinstance(v, (date, datetime)) else str(v)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self, action):
        try:
            self.send_json(200, action())
        except GameError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:   
            self.send_json(500, {"error": f"server error: {e}"})

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise GameError("request too large")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise GameError("bad JSON")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/case":
            self.handle_api(lambda: case_state(parse_qs(url.query).get("id", [""])[0]))
        elif url.path in ("/", "/index.html"):
            page = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        routes = {"/api/new": new_case, "/api/query": run_query, "/api/hint": take_hint, "/api/accuse": accuse}
        action = routes.get(urlparse(self.path).path)
        if action is None:
            self.send_json(404, {"error": "not found"})
            return
        self.handle_api(lambda: action(self.read_body()))

    def log_message(self, fmt, *args):   
        print(f"{self.address_string()} {fmt % args}")


def main():
    ap = argparse.ArgumentParser(description="Simple web front end")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow other machines (e.g. from a VM)")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    print(f"open http://localhost:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
