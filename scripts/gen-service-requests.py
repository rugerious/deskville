#!/usr/bin/env python3
"""Generate synthetic service requests for Deskville (fixed seed, reproducible).

Fully synthetic: no names, emails, phone numbers or street addresses.
Areas are public town names only. Running twice gives byte-identical CSVs.
Output: db/seed/service_requests_<tenant>.csv
"""
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

N = 200
WINDOW_START = datetime(2026, 8, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 112  # up to 2026-11-21

# category -> (doc slug, descriptions)
CATEGORIES = {
    "missed-bin": ("waste-missed-bin", [
        "{bin} bin not emptied on the scheduled day",
        "{bin} bin missed again this week",
        "Whole street's {bin} bins left after collection",
        "{bin} bin emptied but left in the road",
    ]),
    "bulky-collection": ("waste-bulky", [
        "Collection request: old sofa and armchair",
        "Collection request: fridge freezer",
        "Collection request: mattress and bed frame",
        "Booked bulky collection not picked up",
    ]),
    "garden-waste": ("waste-garden", [
        "Garden waste subscription: sticker not received",
        "Garden waste bin not collected",
        "Request for an additional garden waste bin",
    ]),
    "fly-tipping": ("waste-fly-tipping", [
        "Bags of rubbish dumped on the footpath",
        "Builder's rubble left by the canal path",
        "Tyres dumped near the playing field",
        "Household items left in the back alley",
    ]),
    "pothole": ("pothole", [
        "Deep pothole near the bus stop",
        "Pothole on the junction causing cyclists to swerve",
        "Several potholes along the road after the frost",
        "Sunken drain cover in the carriageway",
    ]),
    "parking-permit": ("parking-permits", [
        "Resident permit renewal not received",
        "Visitor permit request",
        "Change of vehicle on resident permit",
    ]),
    "parking-fine": ("parking-fines", [
        "Challenge to a penalty charge notice: signs unclear",
        "Penalty charge paid but reminder received",
        "Challenge to a penalty charge notice: valid permit displayed",
    ]),
    "blue-badge": ("blue-badge", [
        "New Blue Badge application",
        "Blue Badge renewal",
        "Replacement for a lost Blue Badge",
    ]),
}
WEIGHTS = {"missed-bin": 30, "bulky-collection": 12, "garden-waste": 10, "fly-tipping": 14,
           "pothole": 16, "parking-permit": 7, "parking-fine": 6, "blue-badge": 5}
WINDOW_END = WINDOW_START + timedelta(days=WINDOW_DAYS)
# Status depends on age: old requests are mostly finished, new ones mostly open.
STATUS_BY_AGE = [
    (7,    [("received", 50), ("in-progress", 30), ("scheduled", 15), ("resolved", 5)]),
    (30,   [("received", 5), ("in-progress", 35), ("scheduled", 25), ("resolved", 30), ("closed", 5)]),
    (9999, [("in-progress", 5), ("scheduled", 5), ("resolved", 60), ("closed", 30)]),
]

TENANTS = {
    "wigan": {
        "areas": ["Wigan", "Leigh", "Hindley", "Ashton-in-Makerfield", "Atherton", "Tyldesley",
                  "Standish", "Golborne", "Orrell", "Ince", "Shevington", "Lowton"],
        # Wigan bin colours as used in the content docs (the cross-tenant trap)
        "bins": ["Black", "Green", "Blue", "Brown"],
        "ref": lambda i, d: f"WGN-{d:%y}-{i:06d}",
    },
    "bury": {
        "areas": ["Bury", "Radcliffe", "Prestwich", "Whitefield", "Ramsbottom", "Tottington"],
        "bins": ["Grey", "Blue", "Green", "Brown"],
        "ref": lambda i, d: f"BRY/{d:%Y}/{i:05d}",
    },
}

def pick(rng, pairs):
    items, weights = zip(*pairs)
    return rng.choices(items, weights=weights, k=1)[0]

def generate(tenant, cfg):
    rng = random.Random(f"deskville-{tenant}-v1")
    rows = []
    for _ in range(N):
        created = WINDOW_START + timedelta(days=rng.randrange(WINDOW_DAYS),
                                           hours=rng.randint(7, 19), minutes=rng.randrange(60))
        cat = pick(rng, WEIGHTS.items())
        slug, texts = CATEGORIES[cat]
        desc = rng.choice(texts).format(bin=rng.choice(cfg["bins"]))
        age = (WINDOW_END - created).days
        status = pick(rng, next(w for limit, w in STATUS_BY_AGE if age <= limit))
        lag = 0 if status == "received" else rng.randint(1, min(21, max(1, age)))
        updated = created + timedelta(days=lag)
        if lag:  # council updates happen in office hours, never after the window
            updated = updated.replace(hour=rng.randint(9, 16), minute=rng.randrange(60))
        if updated > WINDOW_END:  # too recent for a later update: same-day triage instead
            updated = created + timedelta(minutes=rng.randint(20, 180))
        rows.append({
            "category": cat,
            "status": status,
            "area": rng.choice(cfg["areas"]),
            "description": desc,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
            "doc_id": f"{tenant}-{slug}",
        })
    # References follow creation order, like a real case system.
    rows.sort(key=lambda r: r["created_at"])
    seq = rng.randint(3000, 4000)
    out = []
    for r in rows:
        seq += rng.randint(1, 37)
        out.append({"reference": cfg["ref"](seq, datetime.fromisoformat(r["created_at"])), **r})
    return out

def main():
    out = Path(__file__).resolve().parent.parent / "db" / "seed"
    out.mkdir(parents=True, exist_ok=True)
    for tenant, cfg in TENANTS.items():
        path = out / f"service_requests_{tenant}.csv"
        rows = generate(tenant, cfg)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"{path.name}: {len(rows)} rows")

if __name__ == "__main__":
    main()
