"""

Vardai kol kas iš sąrašų, vėliau planuojame naudoti Faker. Paleisti tik keičiant duomenis:

 python make_base_data.py

"""
from __future__ import annotations

import datetime as dt
import random
import string
from pathlib import Path

SEED = 2026
PEOPLE = 120       # bendros gatvės, mašinos, klubas
REPORTS = 45
MEMBERS = 30
EVENT_GOERS = 40
SMALL_TALK_INTERVIEWS = 10

MALE = """James John Robert Michael William David Richard Joseph Thomas Charles Daniel Matthew
Anthony Mark Donald Steven Paul Andrew Joshua Kenneth Kevin Brian George Timothy Ronald Edward
Jason Jeffrey Ryan Jacob Gary Nicholas Eric Jonathan Stephen Larry Justin Scott Brandon Benjamin
Samuel Gregory Frank Alexander Patrick Raymond Jack Dennis Jerry Tyler""".split()
FEMALE = """Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen Lisa Nancy
Betty Margaret Sandra Ashley Kimberly Emily Donna Michelle Carol Amanda Dorothy Melissa Deborah
Stephanie Rebecca Sharon Laura Cynthia Kathleen Amy Angela Shirley Anna Brenda Pamela Emma Nicole
Helen Samantha Katherine Christine Debra Rachel Carolyn Janet Catherine Maria Heather""".split()
LAST = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez
Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez
Clark Ramirez Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green
Adams Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips Evans Turner Diaz
Parker Cruz Edwards Collins Reyes Stewart Morris Morales Murphy Cook Rogers Gutierrez Ortiz Morgan
Cooper Peterson Bailey Reed Kelly Howard Ramos Kim Cox Ward Richardson""".split()
STREETS = ["Mill Lane", "Oak Lane", "Maple Street", "River Road", "Park Place", "Church Street",
           "Station Road", "Bridge Street", "Orchard Way", "Union Street", "Willow Way", "Queen Street"]

CARS = {
    "Toyota": ["Corolla", "Camry"], "Volkswagen": ["Golf", "Passat"], "Ford": ["Focus", "Mondeo"],
    "Skoda": ["Octavia", "Superb"], "BMW": ["3 Series", "X5"],
}
HAIR = ["black", "brown", "blonde", "red", "grey"]
CITIES = ["SQL City", "Query Town", "Join Harbor"]
EVENTS = ["SQL Symphony Concert", "Midnight Jazz Night", "Charity Run", "Tech Founders Meetup", "Wine Tasting Evening"]
CRIMES = ["theft", "theft", "assault", "vandalism", "fraud", "robbery", "accident"]
REPORT_TEXT = {
    "theft": ["A bicycle was stolen from outside the {p}.", "Several items went missing from the {p}."],
    "assault": ["Two men were fighting outside the {p}. Both left before the patrol arrived."],
    "vandalism": ["Windows were broken at the {p} during the night."],
    "fraud": ["The owner of the {p} reported fake invoices."],
    "robbery": ["The cashier of the {p} was threatened and robbed."],
    "accident": ["A cyclist was hit by a car near the {p}. Minor injuries."],
}
PLACES = ["bakery", "train station", "bank", "pharmacy", "bar", "harbor", "library"]
SMALL_TALK = [
    "I was at home all evening, you can ask my neighbours.",
    "I don't remember anything unusual that week.",
    "I only went out to buy groceries.",
    "I heard sirens, but I did not see anything.",
]
ALNUM = string.ascii_uppercase + string.digits


def ymd(d: dt.date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def inserts(table: str, rows: list[dict], chunk: int = 200) -> str:
    if not rows:
        return ""
    cols = list(rows[0])
    out = []
    for i in range(0, len(rows), chunk):
        values = ",\n".join("(" + ", ".join(sql_value(r[c]) for c in cols) + ")" for r in rows[i:i + chunk])
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};\n")
    return "\n".join(out)


def main() -> None:
    rng = random.Random(SEED)
    start, end = dt.date(2026, 1, 1), dt.date(2026, 10, 1)

    def day() -> dt.date:
        return start + dt.timedelta(days=rng.randint(0, (end - start).days))

    licenses, persons, members, checkins, events, reports, interviews = ([] for _ in range(7))
    names, plates = set(), set()
    person_ids = rng.sample(range(10000, 99999), PEOPLE)
    license_ids = rng.sample(range(100000, 999999), PEOPLE)
    for pid, lid in zip(person_ids, license_ids):
        gender = rng.choice(["male", "female"])
        while (name := f"{rng.choice(MALE if gender == 'male' else FEMALE)} {rng.choice(LAST)}") in names:
            pass
        names.add(name)
        has_license = rng.random() < 0.9
        if has_license:
            while (plate := "".join(rng.choices(ALNUM, k=6))) in plates:
                pass
            plates.add(plate)
            make = rng.choice(list(CARS))
            height = rng.randint(170, 196) if gender == "male" else rng.randint(155, 182)
            licenses.append(dict(id=lid, gender=gender, height=height, hair_color=rng.choice(HAIR),
                                 plate_number=plate, car_make=make, car_model=rng.choice(CARS[make])))
        persons.append(dict(id=pid, name=name, license_id=lid if has_license else None,
                            address_number=rng.randint(1, 120), address_street_name=rng.choice(STREETS)))

    def hhmm(minutes: int) -> int:
        return minutes // 60 * 100 + minutes % 60

    member_ids = set()
    for p in rng.sample(persons, k=MEMBERS):
        while (mid := "".join(rng.choices(ALNUM, k=5))) in member_ids:
            pass
        member_ids.add(mid)
        members.append(dict(id=mid, person_id=p["id"], membership_status=rng.choice(["gold", "silver", "regular"])))
        for _ in range(rng.randint(1, 5)):
            t_in = rng.randint(6 * 60, 20 * 60) // 15 * 15
            checkins.append(dict(membership_id=mid, check_in_date=ymd(day()), check_in_time=hhmm(t_in),
                                 check_out_time=hhmm(t_in + rng.choice([45, 60, 75, 90]))))

    for p in rng.sample(persons, k=EVENT_GOERS):
        for _ in range(rng.randint(1, 3)):
            events.append(dict(person_id=p["id"], event_name=rng.choice(EVENTS), date=ymd(day()),
                               check_in_time=hhmm(rng.randint(17 * 60, 22 * 60) // 5 * 5)))

    for _ in range(REPORTS):
        kind = rng.choice(CRIMES)
        reports.append(dict(date=ymd(day()), type=kind, city=rng.choice(CITIES),
                            description=rng.choice(REPORT_TEXT[kind]).format(p=rng.choice(PLACES))))
    for p in rng.sample(persons, k=SMALL_TALK_INTERVIEWS):
        interviews.append(dict(person_id=p["id"], transcript=rng.choice(SMALL_TALK)))

    parts = [
        "-- Base police archive (generated by make_base_data.py, seed %d). Do not edit by hand.\n" % SEED,
        "SET search_path TO police;\n",
        inserts("drivers_license", licenses), inserts("person", persons),
        inserts("get_fit_now_member", members), inserts("get_fit_now_check_in", checkins),
        inserts("social_media_event_checkin", events), inserts("crime_scene_report", reports),
        inserts("interview", interviews),
    ]
    out = Path(__file__).resolve().parent / "sql" / "police_data.sql"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out} ({len(persons)} persons, {len(reports)} reports)")


if __name__ == "__main__":
    main()
