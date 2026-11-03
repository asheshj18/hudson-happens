#!/usr/bin/env python3
"""Fetch events for Jersey City, Hoboken and Bayonne from free sources.

Writes site/data/events.json. Standard library only — no pip install needed.

Sources:
  - Jersey City municipal calendar (iCal)
  - Bayonne Public Library (LibCal iCal)
  - Hoboken Public Library (Communico JSON)
  - Luma public discover (geo search around Hudson County)
  - Ticketmaster Discovery API (only if TICKETMASTER_API_KEY is set)
  - Eventbrite, per organizer in eventbrite_organizers.txt (only if EVENTBRITE_TOKEN is set)

API keys can go in a .env file next to this project (KEY=value per line).
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
for _line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    if "=" in _line and not _line.lstrip().startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

TZ = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (HudsonHappens event aggregator)"}
OUT = ROOT / "site" / "data" / "events.json"
DAYS_AHEAD = 60
CITIES = ("Jersey City", "Hoboken", "Bayonne")
CENTER = (40.7282, -74.0435)  # between downtown JC and Hoboken


# ---------------------------------------------------------------- helpers
def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def iso(d):
    return d.astimezone(TZ).isoformat() if d else None


# ---------------------------------------------------------------- iCal
def parse_ical_dt(value, params):
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=TZ), True
    if value.endswith("Z"):
        return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc), False
    m = re.search(r"TZID=([^;:]+)", params)
    tz = TZ
    if m:
        try:
            tz = ZoneInfo(m.group(1).strip('"'))
        except Exception:
            pass
    return dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz), False


def ical_unescape(s):
    return s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_ical(text):
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold lines
    events, cur = [], None
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, val = line.split(":", 1)
            name, _, params = key.partition(";")
            cur[name.upper()] = (val, params)
    return events


def from_ical(url, source, city, default_venue=None):
    out = []
    for ev in parse_ical(get(url)):
        if "DTSTART" not in ev or "SUMMARY" not in ev:
            continue
        start, all_day = parse_ical_dt(*ev["DTSTART"])
        end = parse_ical_dt(*ev["DTEND"])[0] if "DTEND" in ev else None
        loc = ical_unescape(ev.get("LOCATION", ("", ""))[0]).strip()
        out.append({
            "id": f"{source}:{ev.get('UID', (ev['SUMMARY'][0] + ev['DTSTART'][0], ''))[0]}",
            "title": ical_unescape(ev["SUMMARY"][0]).strip(),
            "description": strip_html(ical_unescape(ev.get("DESCRIPTION", ("", ""))[0])),
            "start": iso(start),
            "end": iso(end),
            "all_day": all_day,
            "venue": default_venue if default_venue and loc and len(loc) < 30 else (loc or default_venue),
            "address": loc,
            "city": city,
            "url": ev.get("URL", ("", ""))[0] or None,
            "image": None,
            "price": "Free",
            "source": source,
            "raw_tags": [t.strip() for t in ical_unescape(ev.get("CATEGORIES", ("", ""))[0]).split(",") if t.strip()],
        })
    return out


# ---------------------------------------------------------------- sources
def jersey_city_gov():
    return from_ical("https://www.jerseycitynj.gov/ICalendarHandler?calendarId=12409811",
                     "City of Jersey City", "Jersey City")


def bayonne_library():
    evs = from_ical("https://bayonnelibrary.libcal.com/ical_subscribe.php?src=p&cid=17197",
                    "Bayonne Public Library", "Bayonne", default_venue="Bayonne Public Library")
    for e in evs:
        if e["address"] and e["venue"] == "Bayonne Public Library":
            e["address"] = f"{e['address']}, Bayonne Public Library, 697 Avenue C"
    return evs


def hoboken_library():
    req = {"private": False, "date": dt.date.today().isoformat(), "days": DAYS_AHEAD,
           "locations": [], "ages": [], "types": []}
    url = "https://hobokenlibrary.libnet.info/eeventcaldata?event_type=0&req=" + urllib.parse.quote(json.dumps(req))
    out = []
    for e in json.loads(get(url)):
        start = dt.datetime.strptime(e["raw_start_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        end = None
        if e.get("raw_end_time"):
            end = dt.datetime.strptime(e["raw_end_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        img = e.get("event_image") or e.get("image")
        out.append({
            "id": f"hoboken-library:{e['id']}",
            "title": e["title"].strip(),
            "description": strip_html(e.get("long_description") or e.get("description")),
            "start": iso(start), "end": iso(end), "all_day": False,
            "venue": (e.get("venue_name") or e.get("library") or "Hoboken Public Library").strip(),
            "address": strip_html(e.get("venue_description")) or "500 Park Ave, Hoboken",
            "city": "Hoboken",
            "url": e.get("url"),
            "image": f"https://hobokenlibrary.libnet.info/images/events/hobokenlibrary/{img}" if img else None,
            "price": "Free",
            "source": "Hoboken Public Library",
            "raw_tags": [t.strip() for t in (e.get("tags") or "").split(",") + (e.get("ages") or "").split(",") if t.strip()],
        })
    return out


def luma():
    out, cursor = [], None
    for _ in range(15):
        q = {"latitude": CENTER[0], "longitude": CENTER[1], "pagination_limit": 50}
        if cursor:
            q["pagination_cursor"] = cursor
        d = json.loads(get("https://api.lu.ma/discover/get-paginated-events?" + urllib.parse.urlencode(q)))
        for entry in d.get("entries", []):
            ev = entry["event"]
            geo = ev.get("geo_address_info") or {}
            city = geo.get("city")
            if city not in CITIES:
                continue
            ticket = entry.get("ticket_info") or {}
            price = "Free" if ticket.get("is_free") else ("Paid" if ticket else None)
            out.append({
                "id": f"luma:{ev['api_id']}",
                "title": ev["name"].strip(),
                "description": "",
                "start": iso(dt.datetime.fromisoformat(ev["start_at"].replace("Z", "+00:00"))),
                "end": iso(dt.datetime.fromisoformat(ev["end_at"].replace("Z", "+00:00"))) if ev.get("end_at") else None,
                "all_day": False,
                "venue": geo.get("address") or city,
                "address": geo.get("full_address") or geo.get("short_address") or "",
                "city": city,
                "url": f"https://lu.ma/{ev['url']}" if ev.get("url") else None,
                "image": ev.get("cover_url"),
                "price": price,
                "source": "Luma",
                "raw_tags": [],
            })
        cursor = d.get("next_cursor")
        if not d.get("has_more") or not cursor:
            break
    return out


def ticketmaster():
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        print("  (skipped: set TICKETMASTER_API_KEY to enable)", file=sys.stderr)
        return []
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    for page in range(5):
        q = {"apikey": key, "latlong": f"{CENTER[0]},{CENTER[1]}", "radius": 4, "unit": "miles",
             "size": 200, "page": page, "sort": "date,asc",
             "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "endDateTime": (now + dt.timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        d = json.loads(get("https://app.ticketmaster.com/discovery/v2/events.json?" + urllib.parse.urlencode(q)))
        for ev in d.get("_embedded", {}).get("events", []):
            venue = (ev.get("_embedded", {}).get("venues") or [{}])[0]
            city = (venue.get("city") or {}).get("name")
            if city not in CITIES:
                continue
            dates = ev.get("dates", {}).get("start", {})
            if dates.get("dateTime"):
                start = dt.datetime.fromisoformat(dates["dateTime"].replace("Z", "+00:00"))
            elif dates.get("localDate"):
                start = dt.datetime.fromisoformat(dates["localDate"]).replace(tzinfo=TZ)
            else:
                continue
            pr = (ev.get("priceRanges") or [{}])[0]
            imgs = sorted(ev.get("images") or [], key=lambda i: -i.get("width", 0))
            cls = (ev.get("classifications") or [{}])[0]
            out.append({
                "id": f"ticketmaster:{ev['id']}",
                "title": ev["name"].strip(),
                "description": strip_html(ev.get("info") or ev.get("pleaseNote") or ""),
                "start": iso(start), "end": None, "all_day": not dates.get("dateTime"),
                "venue": venue.get("name"),
                "address": (venue.get("address") or {}).get("line1", ""),
                "city": city,
                "url": ev.get("url"),
                "image": imgs[0]["url"] if imgs else None,
                "price": f"${pr['min']:.0f}+" if pr.get("min") else "Paid",
                "source": "Ticketmaster",
                "raw_tags": [x.get("name") for x in (cls.get("segment"), cls.get("genre")) if x and x.get("name") not in (None, "Undefined")],
            })
        if page + 1 >= d.get("page", {}).get("totalPages", 0):
            break
    return out


def eventbrite():
    token = os.environ.get("EVENTBRITE_TOKEN")
    if not token:
        print("  (skipped: set EVENTBRITE_TOKEN to enable)", file=sys.stderr)
        return []
    ids_file = ROOT / "eventbrite_organizers.txt"
    ids = [l.split("#")[0].strip() for l in ids_file.read_text().splitlines()] if ids_file.exists() else []
    ids = [i for i in ids if i]
    if not ids:
        print("  (skipped: add organizer IDs to eventbrite_organizers.txt)", file=sys.stderr)
        return []
    out = []
    for org in ids:
        url = (f"https://www.eventbriteapi.com/v3/organizers/{org}/events/"
               "?status=live&order_by=start_asc&expand=venue,ticket_availability,category")
        while url:
            req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    d = json.loads(r.read())
            except Exception as ex:
                print(f"  eventbrite organizer {org}: {ex}", file=sys.stderr)
                break
            for ev in d.get("events", []):
                venue = ev.get("venue") or {}
                addr = venue.get("address") or {}
                city = (addr.get("city") or "").strip()
                if city not in CITIES and not ev.get("online_event"):
                    continue
                if ev.get("online_event"):
                    continue  # in-person events only
                ta = ev.get("ticket_availability") or {}
                if ev.get("is_free"):
                    price = "Free"
                elif (ta.get("minimum_ticket_price") or {}).get("major_value"):
                    price = f"${float(ta['minimum_ticket_price']['major_value']):.0f}+"
                else:
                    price = "Paid"
                out.append({
                    "id": f"eventbrite:{ev['id']}",
                    "title": (ev.get("name") or {}).get("text", "").strip(),
                    "description": strip_html((ev.get("summary") or (ev.get("description") or {}).get("text") or "")),
                    "start": iso(dt.datetime.fromisoformat(ev["start"]["utc"].replace("Z", "+00:00"))),
                    "end": iso(dt.datetime.fromisoformat(ev["end"]["utc"].replace("Z", "+00:00"))) if ev.get("end") else None,
                    "all_day": False,
                    "venue": venue.get("name"),
                    "address": addr.get("localized_address_display") or addr.get("address_1") or "",
                    "city": city,
                    "url": ev.get("url"),
                    "image": (ev.get("logo") or {}).get("url"),
                    "price": price,
                    "source": "Eventbrite",
                    "raw_tags": [(ev.get("category") or {}).get("short_name")] if ev.get("category") else [],
                })
            pg = d.get("pagination") or {}
            url = (f"https://www.eventbriteapi.com/v3/organizers/{org}/events/?status=live&order_by=start_asc"
                   f"&expand=venue,ticket_availability,category&continuation={pg['continuation']}") if pg.get("has_more_items") else None
    return out


SOURCES = [jersey_city_gov, bayonne_library, hoboken_library, luma, ticketmaster, eventbrite]

# ---------------------------------------------------------------- categorize
# Order matters: first match wins for the primary category, but every match is kept.
CATEGORY_RULES = [
    ("Civic", r"\b(council|caucus|board meeting|planning board|zoning|commission|committee|town hall|hearing|senior freeze|anchor|court outreach|community meeting|ward)\b"),
    ("Kids & Family", r"\b(kids?|children'?s?|storytime|story time|toddler|baby|babies|lapsit|family|teens?|tweens?|ages \d|grades? \d|homework|lego|parent)\b"),
    ("Music", r"\b(concert|music|live band|jazz|dj|orchestra|choir|open mic|karaoke|singer|songwriter|hip.?hop|rock|piano|guitar)\b"),
    ("Comedy", r"\b(comedy|comedian|stand.?up|improv)\b"),
    ("Arts & Culture", r"\b(art|arts|gallery|exhibit|exhibition|museum|painting|drawing|craft|crafts|knit|crochet|theater|theatre|film|movie|screening|poetry|book club|author|reading|writing|photography|dance|ceramics)\b"),
    ("Tech & Business", r"\b(tech|ai|startup|founder|networking|entrepreneur|coding|developer|career|resume|job|business|investor|marketing|linkedin|small business|crypto|product)\b"),
    ("Food & Drink", r"\b(food|dinner|brunch|tasting|wine|beer|brewery|cocktail|cooking|chef|restaurant|farmers'? market|happy hour|coffee|bake)\b"),
    ("Fitness & Wellness", r"\b(yoga|run|running|5k|fitness|workout|pilates|meditation|wellness|health|walk|cycling|bike|tai chi|chi kung|zumba|mental health)\b"),
    ("Learning", r"\b(class|workshop|esl|english|spanish|language|lecture|seminar|course|tutorial|training|computer|citizenship|tax)\b"),
    ("Outdoors", r"\b(park|garden|outdoor|waterfront|cleanup|tree|nature|hike|kayak|boat)\b"),
    ("Sports", r"\b(sports?|game day|basketball|soccer|baseball|hockey|football|chess|mahjong)\b"),
    ("Nightlife", r"\b(party|nightlife|bar crawl|club night|drag|trivia)\b"),
]
TM_SEGMENT = {"Music": "Music", "Sports": "Sports", "Arts & Theatre": "Arts & Culture", "Film": "Arts & Culture",
              "Comedy": "Comedy", "Family": "Kids & Family",
              # Eventbrite category short names
              "Food & Drink": "Food & Drink", "Performing & Visual Arts": "Arts & Culture", "Film & Media": "Arts & Culture",
              "Business": "Tech & Business", "Science & Tech": "Tech & Business", "Health": "Fitness & Wellness",
              "Sports & Fitness": "Fitness & Wellness", "Community": "Community", "Family & Education": "Kids & Family",
              "Nightlife": "Nightlife"}


def categorize(e):
    """Match on title + source tags first; fall back to description only if nothing hits."""
    cats = [TM_SEGMENT[t] for t in e["raw_tags"] if t in TM_SEGMENT]
    primary = " ".join([e["title"], " ".join(e["raw_tags"])]).lower()
    for name, pattern in CATEGORY_RULES:
        if name not in cats and re.search(pattern, primary):
            cats.append(name)
    if not cats:
        desc = e["description"][:300].lower()
        cats = [name for name, pattern in CATEGORY_RULES if re.search(pattern, desc)][:1]
    return cats or ["Community"]


SKIP = re.compile(r"\b(closed|closure|closing early|cancel+ed|postponed)\b", re.I)


# ---------------------------------------------------------------- main
def main():
    events, status = [], {}
    for src in SOURCES:
        name = src.__name__
        try:
            got = src()
            events.extend(got)
            status[name] = len(got)
            print(f"{name:20s} {len(got):4d} events", file=sys.stderr)
        except Exception as ex:  # one broken source shouldn't kill the run
            status[name] = f"error: {ex}"
            print(f"{name:20s} ERROR {ex}", file=sys.stderr)

    now = dt.datetime.now(TZ)
    horizon = now + dt.timedelta(days=DAYS_AHEAD)
    seen, cleaned = set(), []
    for e in sorted(events, key=lambda e: e["start"]):
        start = dt.datetime.fromisoformat(e["start"])
        end = dt.datetime.fromisoformat(e["end"]) if e["end"] else start + dt.timedelta(hours=2)
        if end < now or start > horizon or SKIP.search(e["title"]):
            continue
        key = (re.sub(r"\W+", "", e["title"].lower()), start.date(), e["city"])
        if key in seen:
            continue
        seen.add(key)
        e["categories"] = categorize(e)
        e["description"] = e["description"][:600]
        e["free"] = e["price"] == "Free" or bool(re.search(r"\bfree\b", e["title"].lower()))
        del e["raw_tags"]
        cleaned.append(e)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated": now.isoformat(), "sources": status, "events": cleaned}, indent=1))
    print(f"\nwrote {len(cleaned)} events -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
