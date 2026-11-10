"""Variklis: iš policijos archyvo sukuria bylą"""
import copy
import datetime as dt
import random
import string
from dataclasses import dataclass

from make_base_data import CARS, CITIES, EVENTS, HAIR

ALNUM = string.ascii_uppercase + string.digits
LEVELS = {
    
    "easy":   dict(finalists=2, decoys=2, mm=False, mm_decoys=0),
    "medium": dict(finalists=3, decoys=3, mm=True,  mm_decoys=2),
    "hard":   dict(finalists=4, decoys=4, mm=True,  mm_decoys=3),

}
ALIBIS = ["event", "stolen_car", "back_at_gym", "hospital"]
DECOY_MISSES = ["silver", "late", "car", "short"]


def ymd(d: dt.date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def hhmm(minutes: int) -> int:
    return minutes // 60 * 100 + minutes % 60


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Case:
    briefing: str
    tables: dict      
    solution: dict   
    hints: list       
    messages: dict   
    checks: dict     


def build_case(base: dict, seed: int, attempt: int, level: str) -> Case:
    p = LEVELS[level]
    rng = random.Random(f"{seed}:{attempt}")   # visi atsitiktiniai pasirinkimai ateina iš seed'o
    t = copy.deepcopy(base)
    lic = {l["id"]: l for l in t["drivers_license"]}

    
    city = rng.choice(CITIES)
    day = dt.date(2026, rng.randint(3, 9), rng.randint(3, 25))
    D = ymd(day)
    ws = rng.choice([20 * 60 + 30, 21 * 60, 21 * 60 + 30])   
    we = ws + 30
    gym_out = ws - rng.choice([60, 75, 90])                   
    make = rng.choice(sorted(CARS))
    wh = rng.choice([176, 178, 180])                          

    
    t["get_fit_now_check_in"] = [c for c in t["get_fit_now_check_in"] if c["check_in_date"] != D]
    t["social_media_event_checkin"] = [e for e in t["social_media_event_checkin"] if e["date"] != D]
    t["crime_scene_report"] = [r for r in t["crime_scene_report"]
                               if not (D - 10 <= r["date"] <= D + 1 and r["city"] == city)]

    # Pirma parenka žudiką
    def drivers(gender):
        return [x for x in t["person"] if x["license_id"] and lic[x["license_id"]]["gender"] == gender]
    men = rng.sample(drivers("male"), p["finalists"] + p["decoys"])
    killer, innocents, decoys = men[0], men[1:p["finalists"]], men[p["finalists"]:]
    finalists = [killer, *innocents]
    mastermind, mm_decoys = None, []
    if p["mm"]:
        mastermind, *mm_decoys = rng.sample(drivers("female"), 1 + p["mm_decoys"])
    cast = {x["id"] for x in [*men, *mm_decoys] + ([mastermind] if mastermind else [])}
    victim, w1, w2 = rng.sample([x for x in t["person"] if x["id"] not in cast], 3)

    
    used_ids = {m["id"] for m in t["get_fit_now_member"]}

    def membership(person, status):
       
        old = {m["id"] for m in t["get_fit_now_member"] if m["person_id"] == person["id"]}
        t["get_fit_now_member"] = [m for m in t["get_fit_now_member"] if m["id"] not in old]
        t["get_fit_now_check_in"] = [c for c in t["get_fit_now_check_in"] if c["membership_id"] not in old]
        while (mid := "".join(rng.choices(ALNUM, k=5))) in used_ids:
            pass
        used_ids.add(mid)
        t["get_fit_now_member"].append(dict(id=mid, person_id=person["id"], membership_status=status))
        for _ in range(rng.randint(1, 3)):  
            other = day - dt.timedelta(days=rng.randint(2, 60))
            start = rng.randint(7 * 60, 19 * 60) // 15 * 15
            visit(mid, ymd(other), start, start + 60)
        return mid

    def visit(mid, date, t_in, t_out):
        t["get_fit_now_check_in"].append(dict(membership_id=mid, check_in_date=date,
                                              check_in_time=hhmm(t_in), check_out_time=hhmm(t_out)))

    def car(person, car_make=None, height=None):
        l = lic[person["license_id"]]
        l["car_make"] = car_make or make
        l["car_model"] = rng.choice(CARS[l["car_make"]])
        if height is not None:
            l["height"] = height

    def left_gym_around():
        return gym_out + rng.choice([-15, -10, -5, 0, 5, 10, 15])

    def interview(person, text):
        t["interview"].append(dict(person_id=person["id"], transcript=text))

    def report(date, kind, text):
        t["crime_scene_report"].append(dict(date=date, type=kind, city=city, description=text))

    def tall():
        return rng.randint(wh + 4, wh + 14)

    speakers = {x["id"] for x in [w1, w2, *finalists, *decoys]}
    t["interview"] = [i for i in t["interview"] if i["person_id"] not in speakers]

    
    for f in finalists:
        car(f, height=tall())
        out = left_gym_around()
        visit(membership(f, "gold"), D, out - rng.choice([60, 75, 90]), out)

    #  decoy'ai neatitinka vieno argumento
    for i, d in enumerate(decoys):
        miss = DECOY_MISSES[i % len(DECOY_MISSES)]
        other_make = rng.choice([m for m in sorted(CARS) if m != make])
        car(d, car_make=other_make if miss == "car" else None,
            height=rng.randint(wh - 10, wh - 3) if miss == "short" else tall())
        out = we + rng.randint(30, 90) if miss == "late" else left_gym_around()
        visit(membership(d, "silver" if miss == "silver" else "gold"), D, out - 90, out)
      
        interview(d, {
            "silver": "I trained after work and went straight home. I was alone the whole evening.",
            "late": "I always stay for the late class at Get Fit Now. That night too, until closing.",
            "car": "After the gym I drove around a bit to clear my head, then went home. I live alone.",
            "short": "I had a headache, so I left the gym early and slept the rest of the evening.",
        }[miss])

    
    regulars = [m for m in t["get_fit_now_member"] if m["person_id"] not in cast | {w1["id"], w2["id"]}]
    for m in rng.sample(regulars, min(3, len(regulars))):
        start = rng.randint(7 * 60, 11 * 60) // 15 * 15
        visit(m["id"], D, start, start + 60)

    
    street1 = victim["address_street_name"]
    others = sorted({x["address_street_name"] for x in t["person"]} - {street1})
    street2 = rng.choice(others)
    first = w2["name"].split()[0]
    for x in t["person"]:
        if x["address_street_name"] == street2 and x["name"].split()[0] == first and x is not w2:
            x["address_street_name"] = rng.choice([s for s in others if s != street2])
    w2["address_street_name"] = street2
    w1["address_street_name"] = street1
    w1["address_number"] = max(x["address_number"] for x in t["person"]
                               if x["address_street_name"] == street1 and x is not w1) + rng.randint(1, 9)
    w2_visit_out = gym_out + 5
    visit(membership(w2, "regular"), D, w2_visit_out - 60, w2_visit_out)

    interview(w1, f"Around {clock(ws + 10)} I heard shouting next door, at {victim['name'].split()[0]}'s. "
                  f"Then a man came out in a hurry. He was tall, taller than me, and I'm {wh} cm. "
                  f"He had one of those gold Get Fit Now bags, the ones only gold members get. "
                  f"He drove off in a {make}, I think. It was dark, so I didn't see the plate. "
                  f"Maybe he had a beard, I'm not sure.")
    interview(w2, f"I was at Get Fit Now that evening. When I was leaving, at about {clock(gym_out)}, "
                  f"a tall man walked out just ahead of me. He looked angry and kept checking his phone. "
                  f"I've seen him there before, but I don't know his name.")

    
    alibi_kinds = rng.sample(ALIBIS, len(innocents))
    event = rng.choice(EVENTS)
    for f, kind in zip(innocents, alibi_kinds):
        l = lic[f["license_id"]]
        if kind == "event":
            t["social_media_event_checkin"].append(dict(person_id=f["id"], event_name=event, date=D,
                                                    check_in_time=hhmm(ws + rng.randint(0, 25))))
            interview(f, f"After the gym I went home to change and then to the {event}. "
                         f"I stayed there until it ended, around midnight.")
        elif kind == "stolen_car":
            stolen = day - dt.timedelta(days=rng.randint(2, 4))
            report(ymd(stolen), "theft", f"{f['name']} reported that his {l['car_make']} {l['car_model']} "
                                         f"was stolen from outside his home on {f['address_street_name']}.")
            interview(f, "My car was stolen a few days before that. I took the bus to the gym "
                         "and back home. I didn't go out again.")
        elif kind == "back_at_gym":
            visit(next(m["id"] for m in t["get_fit_now_member"] if m["person_id"] == f["id"]),
                  D, ws - rng.randint(10, 30), we + rng.randint(30, 60))
            interview(f, "I trained in the afternoon, went to eat something nearby and came back "
                         "to the gym for the evening class. I stayed until they closed.")
        else:   # ligoninė
            at = ws + rng.randint(5, 25)
            report(D, "accident", f"{f['name']} slipped on wet stairs at the train station and was taken "
                                  f"to the city hospital at {clock(at)}. He was kept there overnight.")
            interview(f, "I fell at the station that evening and hurt my ankle. "
                         "I spent the night at the hospital.")
    
    cover = rng.choice(EVENTS)
    t["social_media_event_checkin"].append(dict(person_id=killer["id"], event_name=cover, date=D,
                                            check_in_time=hhmm(we + rng.randint(20, 50))))
    interview(killer, f"I didn't go to the gym that day, I haven't been there for weeks. "
                      f"That evening I was at the {cover}, from early on.")

    
    vic_addr = f"{victim['address_number']} {street1}"
    report(ymd(day - dt.timedelta(days=rng.randint(12, 40))), "assault",
           f"Neighbours called the police about a fight outside {vic_addr}. {victim['name']} told officers "
           f"that {killer['name']} owed money and had made threats. Nobody was arrested.")
    herring = innocents[0]
    report(ymd(day - dt.timedelta(days=rng.randint(12, 60))), "vandalism",
           f"{herring['name']} told police that {victim['name']} had scratched his car after an "
           f"argument about a parking space. No damage could be proven.")

    # Žmogžudystės ataskaita
    report(D, "murder", f"{victim['name']} was found dead at home, {vic_addr}. Time of death: between "
                        f"{clock(ws)} and {clock(we)}. A neighbour who lives at the last house on "
                        f"\"{street1}\" saw a man leave. A second witness, named {first}, who lives on "
                        f"\"{street2}\", saw the same man earlier that evening.")

    
    mm = None
    if mastermind:
        mm_event = rng.choice([e for e in EVENTS if e != event])
        month = (day.replace(day=1) - dt.timedelta(days=rng.randint(31, 90))).replace(day=1)
        mkey = month.year * 100 + month.month
        t["social_media_event_checkin"] = [e for e in t["social_media_event_checkin"]
                                       if not (e["event_name"] == mm_event and e["date"] // 100 == mkey)]
        times = rng.randint(3, 4)
        mm_make = rng.choice(sorted(CARS))
        look = dict(hair_color=rng.choice(HAIR), car_make=mm_make, car_model=rng.choice(CARS[mm_make]),
                    height=rng.randint(160, 178))

        def attend(person, n):
            for d in rng.sample(range(1, 29), n):
                t["social_media_event_checkin"].append(dict(person_id=person["id"], event_name=mm_event,
                                                        date=ymd(month.replace(day=d)), check_in_time=1900))
        lic[mastermind["license_id"]].update(look)
        attend(mastermind, times)
        for i, d in enumerate(mm_decoys):
            if i % 2 == 0:   
                lic[d["license_id"]].update(look)
                attend(d, rng.randint(1, times - 1))
            else:           
                other = rng.choice([m for m in sorted(CARS) if m != mm_make])
                lic[d["license_id"]].update(look, car_make=other, car_model=CARS[other][0])
                attend(d, times)
        lo, hi = look["height"] - 2, look["height"] + 2
        report(ymd(day + dt.timedelta(days=1)), "tip",
               f"Anonymous call about the {victim['name']} case: the killer was paid by a woman, around "
               f"{lo}-{hi} cm tall, with {look['hair_color']} hair, who drives a {mm_make} {look['car_model']}. "
               f"The caller says she went to the {mm_event} {times} times in {month:%B %Y}.")
        mm = dict(event=mm_event, month=mkey, times=times, lo=lo, hi=hi, **look)

    briefing = (f"A murder happened on {day:%B} {day.day}, {day.year} in {city}. "
                f"Find the killer" + (" and the person who paid him." if mastermind else "."))
    hints = [
        f"crime_scene_report: type = 'murder' AND city = '{city}' AND date = {D}.",
        f"Witness 1 lives at the last house on '{street1}' (ORDER BY address_number DESC). "
        f"Witness 2: name LIKE '{first} %' on '{street2}'. Read their interviews.",
        f"The description fits several men: gold members with a visit on {D} who left around "
        f"{clock(gym_out)}, drive a {make} and are taller than {wh} cm. JOIN get_fit_now_member, "
        f"get_fit_now_check_in, person and drivers_license.",
        "Read each suspect's interview, then check his story: social_media_event_checkin, "
        "crime_scene_report and get_fit_now_check_in for that day.",
        f"Who had a reason? crime_scene_report WHERE description LIKE '%{victim['name']}%'.",
        "The killer has no alibi, and the gym records contradict what he said.",
    ]
    solution = {"killer": killer["name"]}
    messages = {"killer": "Correct. The evidence holds: no alibi, a lie about the gym, and a motive."}
    if mastermind:
        hints += ["Someone paid the killer. Look for reports filed after the murder.",
                  f"social_media_event_checkin: event_name = '{mm['event']}' AND date / 100 = {mm['month']}, "
                  f"GROUP BY person_id HAVING count(*) = {mm['times']}; then match height, hair and car."]
        solution["mastermind"] = mastermind["name"]
        messages["killer"] += " But he was paid. Look for reports filed after the murder."
        messages["mastermind"] = "Correct, you found who paid for the murder."
    checks = dict(date=D, city=city, street1=street1, street2=street2, w1=w1["id"], w2=w2["id"], first=first,
                  out_lo=hhmm(gym_out - 20), out_hi=hhmm(gym_out + 20), make=make, wh=wh,
                  ws=hhmm(ws), we=hhmm(we), week_before=ymd(day - dt.timedelta(days=7)),
                  victim=victim["name"], finalists=sorted(x["name"] for x in finalists),
                  innocents=sorted(x["name"] for x in innocents), mm=mm, **solution)
    return Case(briefing, t, solution, hints, messages, checks)



VERIFY_SQL = {
    "report": """SELECT count(*) FROM crime_scene_report
                 WHERE type = 'murder' AND city = %(city)s AND date = %(date)s""",
    "witness1": """SELECT id FROM person WHERE address_street_name = %(street1)s
                   ORDER BY address_number DESC LIMIT 1""",
    "witness2": """SELECT id FROM person
                   WHERE address_street_name = %(street2)s AND name LIKE %(first)s || ' %%'""",
    
    "suspects": """SELECT DISTINCT p.name
                   FROM get_fit_now_member m
                   JOIN get_fit_now_check_in c ON c.membership_id = m.id
                   JOIN person p ON p.id = m.person_id
                   JOIN drivers_license d ON d.id = p.license_id
                   WHERE m.membership_status = 'gold' AND c.check_in_date = %(date)s
                     AND c.check_out_time BETWEEN %(out_lo)s AND %(out_hi)s
                     AND d.car_make = %(make)s AND d.height > %(wh)s AND d.gender = 'male'
                   ORDER BY 1""",
    
    "alibis": """SELECT p.name FROM person p WHERE p.name = ANY(%(finalists)s) AND (
                     EXISTS (SELECT 1 FROM social_media_event_checkin e WHERE e.person_id = p.id
                             AND e.date = %(date)s AND e.check_in_time BETWEEN %(ws)s AND %(we)s)
                  OR EXISTS (SELECT 1 FROM crime_scene_report r WHERE r.type IN ('theft', 'accident')
                             AND r.date BETWEEN %(week_before)s AND %(date)s
                             AND r.description LIKE p.name || ' %%')
                  OR EXISTS (SELECT 1 FROM get_fit_now_member m
                             JOIN get_fit_now_check_in c ON c.membership_id = m.id
                             WHERE m.person_id = p.id AND c.check_in_date = %(date)s
                               AND c.check_in_time <= %(ws)s AND c.check_out_time >= %(we)s))
                 ORDER BY 1""",
    
    "motive": """SELECT p.name FROM person p
                 WHERE p.name <> %(victim)s AND EXISTS (
                     SELECT 1 FROM crime_scene_report r WHERE r.date < %(date)s
                       AND r.description LIKE '%%' || %(victim)s || '%%'
                       AND r.description LIKE '%%' || p.name || '%%')
                 ORDER BY 1""",
    "mastermind": """SELECT p.name
                     FROM person p
                     JOIN drivers_license d ON d.id = p.license_id
                     JOIN (SELECT person_id FROM social_media_event_checkin
                           WHERE event_name = %(event)s AND date / 100 = %(month)s
                           GROUP BY person_id HAVING count(*) = %(times)s) e ON e.person_id = p.id
                     WHERE d.gender = 'female' AND d.hair_color = %(hair_color)s
                       AND d.height BETWEEN %(lo)s AND %(hi)s
                       AND d.car_make = %(car_make)s AND d.car_model = %(car_model)s""",
}


def verify_sql(cur, c: dict) -> list:
    
    args = dict(c, **(c["mm"] or {}))

    def names(step):
        return [r[0] for r in cur.execute(VERIFY_SQL[step], args)]

    failed = []
    if names("report") != [1]:
        failed.append("report")
    if names("witness1") != [c["w1"]]:
        failed.append("witness1")
    if names("witness2") != [c["w2"]]:
        failed.append("witness2")
    suspects = names("suspects")
    if suspects != c["finalists"] or len(suspects) < 2:      # tinka keli, o ne vienas
        failed.append("suspects")
    if names("alibis") != c["innocents"]:                     # alibi turi visi, išskyrus žudiką
        failed.append("alibis")
    motive = names("motive")
    if c["killer"] not in motive or len(motive) < 2:          
        failed.append("motive")
    if c["mm"] and names("mastermind") != [c["mastermind"]]:
        failed.append("mastermind")
    return failed
