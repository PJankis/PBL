"""Scenario engine: turns the fixed police archive into a fresh murder case.

Algorithm (one attempt):
  1. copy the base tables and draw the clues (city, dates, gym prefix, plate part) from the seed;
  2. change base rows that would match a clue by accident;
  3. cast existing people: the killer first, then decoys, witnesses, victim;
  4. rewrite their facts so the evidence leads to the killer, and make every
     decoy fail exactly one clue;
  5. write the crime report, the interviews and the hints.
detective.py loads the case into its own schema and runs the player's clue path
as SQL (VERIFY_SQL). If a stage does not have exactly one answer, the next
attempt is built. Same seed, same case.
"""
import copy
import datetime as dt
import random
import string
from dataclasses import dataclass

from make_base_data import CARS, CITIES, EVENTS, HAIR, STREETS

ALNUM = string.ascii_uppercase + string.digits
LEVELS = {
    #          killer decoys  mastermind  mastermind decoys  plate fragment length
    "easy":   dict(decoys=2, mm=False, mm_decoys=0, frag=4),
    "medium": dict(decoys=4, mm=True,  mm_decoys=2, frag=4),
    "hard":   dict(decoys=6, mm=True,  mm_decoys=4, frag=3),
}


def ymd(d: dt.date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


@dataclass
class Case:
    briefing: str
    tables: dict      # table name -> list of rows
    solution: dict    # stage -> name, in order: killer, then mastermind
    hints: list       # vague to direct, in clue order
    messages: dict    # stage -> text shown when it is solved
    checks: dict      # clue values used by VERIFY_SQL


def build_case(base: dict, seed: int, attempt: int, level: str) -> Case:
    p = LEVELS[level]
    rng = random.Random(f"{seed}:{attempt}")   # every random choice comes from the seed
    t = copy.deepcopy(base)
    lic = {l["id"]: l for l in t["drivers_license"]}

    # 1. Clues.
    city = rng.choice(CITIES)
    murder = dt.date(2026, rng.randint(1, 9), rng.randint(1, 28))
    gym = murder - dt.timedelta(days=rng.randint(3, 8))
    prefix = f"{rng.randint(10, 99)}{rng.choice(string.ascii_uppercase)}"
    frag = "".join(rng.choices(ALNUM, k=p["frag"]))

    def plate(with_frag: bool) -> str:
        while True:
            if with_frag:
                left = rng.randint(0, 6 - len(frag))
                s = "".join(rng.choices(ALNUM, k=left)) + frag + "".join(rng.choices(ALNUM, k=6 - len(frag) - left))
            else:
                s = "".join(rng.choices(ALNUM, k=6))
            if with_frag or frag not in s:
                return s

    # 2. No base row may match the plate clue by accident.
    for l in t["drivers_license"]:
        if frag in l["plate_number"]:
            l["plate_number"] = plate(False)

    # 3. Cast people from the archive. The killer comes first.
    def drivers(gender):
        return [x for x in t["person"] if x["license_id"] and lic[x["license_id"]]["gender"] == gender]
    killer, *decoys = rng.sample(drivers("male"), 1 + p["decoys"])
    mastermind, mm_decoys = None, []
    if p["mm"]:
        mastermind, *mm_decoys = rng.sample(drivers("female"), 1 + p["mm_decoys"])
    cast = {x["id"] for x in [killer, mastermind, *decoys, *mm_decoys] if x}
    victim, w1, w2 = rng.sample([x for x in t["person"] if x["id"] not in cast], 3)

    def make_suspect(person, status, day, plate_matches):
        """Membership with the prefix (or none), a gym visit on `day`, a plate with/without the fragment."""
        lic[person["license_id"]]["plate_number"] = plate(plate_matches)
        old = {m["id"] for m in t["get_fit_now_member"] if m["person_id"] == person["id"]}
        t["get_fit_now_member"] = [m for m in t["get_fit_now_member"] if m["id"] not in old]
        t["get_fit_now_check_in"] = [c for c in t["get_fit_now_check_in"] if c["membership_id"] not in old]
        if status:
            used = {m["id"] for m in t["get_fit_now_member"]}
            while (mid := prefix + "".join(rng.choices(ALNUM, k=2))) in used:
                pass
            t["get_fit_now_member"].append(dict(id=mid, person_id=person["id"], membership_status=status))
            t["get_fit_now_check_in"].append(dict(membership_id=mid, check_in_date=ymd(day)))

    # 4a. The killer matches every clue; each decoy misses exactly one.
    make_suspect(killer, "gold", gym, True)
    misses = [("gold", gym, False),                           # wrong plate
              ("silver", gym, True),                          # not gold
              ("gold", gym - dt.timedelta(days=1), True),     # at the gym on another day
              (None, None, True)]                             # not a member
    for i, d in enumerate(decoys):
        make_suspect(d, *misses[i % len(misses)])

    # 4b. Witnesses: the first lives in the last house on street1, the second is
    #     the only person with that first name on street2.
    street1, street2 = rng.sample(STREETS, 2)
    first = w2["name"].split()[0]
    for x in t["person"]:
        if x["address_street_name"] == street2 and x["name"].split()[0] == first:
            x["address_street_name"] = street1          # move namesakes away
    w2["address_street_name"] = street2
    w1["address_street_name"] = street1
    w1["address_number"] = max(x["address_number"] for x in t["person"]
                               if x["address_street_name"] == street1 and x is not w1) + rng.randint(1, 50)

    # 4c. Mastermind: a woman with a known look, car and event habit.
    killer_says, mm = "I want a lawyer. I'm not saying anything else.", None
    if mastermind:
        event = rng.choice(EVENTS)
        month = (murder.replace(day=1) - dt.timedelta(days=rng.randint(31, 120))).replace(day=1)
        mkey = month.year * 100 + month.month
        t["facebook_event_checkin"] = [e for e in t["facebook_event_checkin"]   # clear accidental matches
                                       if not (e["event_name"] == event and e["date"] // 100 == mkey)]
        times = rng.randint(3, 4)
        make = rng.choice(list(CARS))
        look = dict(hair_color=rng.choice(HAIR), car_make=make, car_model=rng.choice(CARS[make]),
                    height=rng.randint(160, 180))

        def attend(person, n):
            for d in rng.sample(range(1, 29), n):
                t["facebook_event_checkin"].append(dict(person_id=person["id"], event_name=event,
                                                        date=ymd(month.replace(day=d))))
        lic[mastermind["license_id"]].update(look)
        attend(mastermind, times)
        for i, d in enumerate(mm_decoys):
            if i % 2 == 0:   # same look and car, fewer visits
                lic[d["license_id"]].update(look)
                attend(d, rng.randint(1, times - 1))
            else:            # same visits, different car
                other = rng.choice([m for m in CARS if m != make])
                lic[d["license_id"]].update(look, car_make=other, car_model=CARS[other][0])
                attend(d, times)
        lo, hi = look["height"] - 2, look["height"] + 2
        killer_says = (f"I was hired by a woman. I don't know her name, but she is around {lo}-{hi} cm "
                       f"tall, has {look['hair_color']} hair and drives a {make} {look['car_model']}. "
                       f"She attended the {event} {times} times in {month:%B %Y}.")
        mm = dict(event=event, month=mkey, times=times, lo=lo, hi=hi, **look)

    # 5. Texts the player reads.
    speakers = {w1["id"], w2["id"], killer["id"]}
    t["interview"] = [i for i in t["interview"] if i["person_id"] not in speakers]
    t["interview"] += [
        dict(person_id=w1["id"], transcript=(
            f'I heard a gunshot and saw a man run out with a "Get Fit Now Gym" bag. The membership number '
            f'on the bag started with "{prefix}". Only gold members have those bags. He got into a car '
            f'with a plate that included "{frag}".')),
        dict(person_id=w2["id"], transcript=(
            f"I recognized the killer from my gym. I was working out there on {gym:%B} {gym.day}.")),
        dict(person_id=killer["id"], transcript=killer_says),
    ]
    date = ymd(murder)
    t["crime_scene_report"] = [r for r in t["crime_scene_report"]
                               if (r["date"], r["type"], r["city"]) != (date, "murder", city)]
    t["crime_scene_report"].append(dict(date=date, type="murder", city=city, description=(
        f'{victim["name"]} was found dead. There were 2 witnesses. The first lives at the last house '
        f'on "{street1}". The second, named {first}, lives somewhere on "{street2}".')))

    briefing = (f"A murder happened on {murder:%B} {murder.day}, {murder.year} in {city}. "
                f"Find the killer" + (" and who hired them." if mastermind else "."))
    hints = [
        f"crime_scene_report: type = 'murder' AND city = '{city}' AND date = {date}",
        f"Witness 1: address_street_name = '{street1}' ORDER BY address_number DESC. "
        f"Witness 2: name LIKE '{first} %' on '{street2}'",
        "Read both witnesses' rows in interview (interview.person_id = person.id)",
        f"get_fit_now_member id LIKE '{prefix}%' AND membership_status = 'gold', "
        f"checked in on {ymd(gym)}, plate_number LIKE '%{frag}%' (JOIN person -> drivers_license)",
    ]
    solution = {"killer": killer["name"]}
    messages = {"killer": "Correct, that's the killer!"}
    if mastermind:
        hints += ["Read the killer's interview.",
                  f"facebook_event_checkin: event_name = '{mm['event']}', date / 100 = {mm['month']}, "
                  f"GROUP BY person_id HAVING count(*) = {mm['times']}; then match hair, height and car"]
        solution["mastermind"] = mastermind["name"]
        messages["killer"] += " But someone hired them. Read the killer's interview."
        messages["mastermind"] = "Correct, you found who was really behind it!"
    checks = dict(date=date, city=city, street1=street1, street2=street2, w1=w1["id"], w2=w2["id"],
                  first=first, prefix=prefix, frag=frag, gym=ymd(gym), mm=mm, **solution)
    return Case(briefing, t, solution, hints, messages, checks)


# The player's clue path, as SQL. A case is kept only if every step
# returns exactly the expected single answer.
VERIFY_SQL = {
    "report": """SELECT count(*) FROM crime_scene_report
                 WHERE type = 'murder' AND city = %(city)s AND date = %(date)s""",
    "witness1": """SELECT id FROM person WHERE address_street_name = %(street1)s
                   ORDER BY address_number DESC LIMIT 1""",
    "witness2": """SELECT id FROM person
                   WHERE address_street_name = %(street2)s AND name LIKE %(first)s || ' %%'""",
    "killer": """SELECT DISTINCT p.name
                 FROM get_fit_now_member m
                 JOIN get_fit_now_check_in c ON c.membership_id = m.id
                 JOIN person p ON p.id = m.person_id
                 JOIN drivers_license d ON d.id = p.license_id
                 WHERE m.id LIKE %(prefix)s || '%%' AND m.membership_status = 'gold'
                   AND c.check_in_date = %(gym)s AND d.plate_number LIKE '%%' || %(frag)s || '%%'""",
    "mastermind": """SELECT p.name
                     FROM person p
                     JOIN drivers_license d ON d.id = p.license_id
                     JOIN (SELECT person_id FROM facebook_event_checkin
                           WHERE event_name = %(event)s AND date / 100 = %(month)s
                           GROUP BY person_id HAVING count(*) = %(times)s) e ON e.person_id = p.id
                     WHERE d.gender = 'female' AND d.hair_color = %(hair_color)s
                       AND d.height BETWEEN %(lo)s AND %(hi)s
                       AND d.car_make = %(car_make)s AND d.car_model = %(car_model)s""",
}


def verify_sql(cur, c: dict) -> list:
    """Run the clue path inside the case schema; return the names of failed steps."""
    args = dict(c, **(c["mm"] or {}))
    expected = {"report": [1], "witness1": [c["w1"]], "witness2": [c["w2"]], "killer": [c["killer"]]}
    if c["mm"]:
        expected["mastermind"] = [c["mastermind"]]
    return [step for step, want in expected.items()
            if [r[0] for r in cur.execute(VERIFY_SQL[step], args)] != want]
