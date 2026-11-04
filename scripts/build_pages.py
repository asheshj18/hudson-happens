#!/usr/bin/env python3
"""Build crawlable static pages from the event data.

The app at / is a single-page app with #hash routes, which search engines can't index.
This writes real HTML pages next to it, all with content in the markup:

  /events/<slug>/                       one page per event, with schema.org Event JSON-LD
  /<city>/  + /<city>/this-weekend/ ... landing pages that match what people search for
  /this-weekend/, /free/, /tonight/ ... the same across all three towns
  /venues/ + /venues/<slug>/            venues with 2+ upcoming events
  /sitemap.xml, /robots.txt

Runs at the end of fetch_events.py, or on its own (reads site/data/events.json):
    python3 scripts/build_pages.py
Standard library only.
"""
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = SITE / "data" / "events.json"
BASE = "https://hudsonhappens.com"
TZ = ZoneInfo("America/New_York")
WINDOW_DAYS = 30
LIST_CAP = 150

CITIES = [
    {"name": "Jersey City", "slug": "jersey-city", "cls": "jc",
     "intro": "Downtown, the Heights, Journal Square, Bergen-Lafayette and the waterfront. Concerts at Loew's, "
              "gallery nights, markets, library programs and everything in between."},
    {"name": "Hoboken", "slug": "hoboken", "cls": "hob",
     "intro": "The mile square, one PATH stop from Manhattan. Live music on Washington Street, Stevens shows and "
              "games, story times, trivia nights and waterfront events."},
    {"name": "Bayonne", "slug": "bayonne", "cls": "bay",
     "intro": "The peninsula on the Kill van Kull. Library programs, family events, classes and community "
              "gatherings from 1st Street to 56th."},
]
CITY_BY_NAME = {c["name"]: c for c in CITIES}

# Generated top-level paths under site/. Wiped and rebuilt every run; nothing else is touched.
GENERATED = ["events", "venues", "this-weekend", "tonight", "free", "kids", "live-music", "sitemap.xml", "robots.txt", "404.html"] + [c["slug"] for c in CITIES]

# Events we list but keep out of search and the sitemap (ad-network friendliness).
NOINDEX = re.compile(r"strip(per|pers|club)|male revue|gentlemen'?s club|xxx|\b18\+ only", re.I)
ADMIN = re.compile(r"registration|drop-in|book a librarian|board of trustees|office hours|meeting of", re.I)
GENERIC_VENUE = re.compile(r"^(online|virtual|zoom.*|offsite|tba|tbd|various|multiple locations|see description|jersey city|hoboken|bayonne|classroom.*|room .*|.*\bnj\b.*\d{5}.*)$", re.I)

esc = lambda s: html.escape(str(s or ""), quote=True)


def ld_json(x):
    """JSON for a <script> block; escape "</" so text can't close the tag."""
    return json.dumps(x, ensure_ascii=False).replace("</", "<\\/")


def slugify(s, n=60):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-") or "event"


def venue_name(v):
    return (v or "").split(",")[0].strip()


def event_path(e, start):
    h = hashlib.sha1(e["id"].encode()).hexdigest()[:6]
    return f"/events/{slugify(e['title'], 55)}-{start.strftime('%b').lower()}-{start.day}-{h}/"


def assign_paths(events):
    for e in events:
        e["path"] = event_path(e, dt.datetime.fromisoformat(e["start"]).astimezone(TZ))
    return events


# ---------------------------------------------------------------- formatting
def fmt_time(d):
    return d.strftime("%I:%M %p").lstrip("0")


def fmt_day_long(d):
    return f"{d.strftime('%A, %B')} {d.day}"


def fmt_day_short(d):
    return f"{d.strftime('%a, %b')} {d.day}"


def price_text(e):
    if e.get("free"):
        return "Free"
    p = e.get("price")
    return p if p and p != "Paid" else ""


def weekend_range(today):
    d = today.weekday()  # Mon=0 .. Sun=6
    if d == 6:
        return today, today
    if d == 5:
        return today, today + dt.timedelta(days=1)
    start = today if d == 4 else today + dt.timedelta(days=4 - d)
    return start, today + dt.timedelta(days=6 - d)


def summary(e):
    """One original sentence about the event, used for meta descriptions and the page intro."""
    s, cat = e["_start"], (e["categories"][0] if e["categories"] else "Community").lower()
    when = fmt_day_long(s) + ("" if e["all_day"] else f" at {fmt_time(s)}")
    where = venue_name(e.get("venue")) or e["city"]
    p = price_text(e)
    price = " Free to attend." if p == "Free" else f" Tickets from {p.rstrip('+')}." if p.startswith("$") and p not in ("$0+",) else ""
    place = where if where == e["city"] else f"{where} in {e['city']}"
    return f"{e['title']}: a {cat} event at {place}, {when}.{price}"


# ---------------------------------------------------------------- page shell
HEADER = """<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <div class="topbar-inner">
    <a class="logo" href="/" aria-label="Hudson Happens home"><svg viewBox="0 0 28 20" width="28" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M2 6q3-3 6 0t6 0 6 0 6 0M2 12q3-3 6 0t6 0 6 0 6 0M2 18q3-3 6 0t6 0 6 0 6 0"/></svg>Hudson <span>Happens</span></a>
    <button type="button" class="menu-btn" aria-label="Open menu" aria-expanded="false" aria-controls="mainnav">
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path class="l1" d="M4 7h16"/><path class="l2" d="M4 12h16"/><path class="l3" d="M4 17h16"/></svg>
    </button>
    <nav class="mainnav" id="mainnav" aria-label="Main">
      <form class="nav-search" role="search" data-search>
        <label class="sr-only" for="nav-q">Search events</label>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m20 20-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        <input id="nav-q" name="q" type="search" placeholder="Search the calendar…" autocomplete="off">
      </form>
      <a href="/#/events">All events</a>
      <a href="/venues/">Venues</a>
      <a href="/tonight/">Tonight</a>
      <a href="/this-weekend/">Weekend</a>
      <a href="/free/" class="nav-free">Free</a>
      <a href="/#/saved">Saved</a>
      <a href="/#/pick">Help me pick</a>
      <a href="/#/spontaneous">Surprise me</a>
    </nav>
    <form class="topsearch" role="search" data-search>
      <label class="sr-only" for="top-q">Search events</label>
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m20 20-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      <input id="top-q" name="q" type="search" placeholder="Search the calendar…" autocomplete="off">
    </form>
  </div>
</header>"""


def footer():
    towns = "".join(f'<li><a href="/{c["slug"]}/">Things to do in {esc(c["name"])}</a></li>' for c in CITIES)
    weekend = "".join(f'<li><a href="/{c["slug"]}/this-weekend/">{esc(c["name"])} this weekend</a></li>' for c in CITIES)
    free = "".join(f'<li><a href="/{c["slug"]}/free/">Free in {esc(c["name"])}</a></li>' for c in CITIES)
    return f"""<footer class="footer"><div class="footer-inner">
  <div><h4>Towns</h4><ul>{towns}</ul></div>
  <div><h4>This weekend</h4><ul>{weekend}<li><a href="/this-weekend/">Everywhere this weekend</a></li></ul></div>
  <div><h4>Free &amp; family</h4><ul>{free}<li><a href="/kids/">With the kids</a></li><li><a href="/live-music/">Live music</a></li></ul></div>
  <div><h4>Hudson Happens</h4><p>Events across Jersey City, Hoboken and Bayonne in one calendar, updated three times a day.</p>
  <p>Details come from each organizer. Check the original listing before you go.</p><p><a href="/venues/">All venues</a> · <a href="/">Home</a></p></div>
</div></footer>"""


def page(*, path, title, description, body, jsonld=None, image=None, noindex=False, og_type="website"):
    url = BASE + path
    img = image or f"{BASE}/og.png"
    ld = "".join(f'<script type="application/ld+json">{ld_json(x)}</script>\n' for x in (jsonld or []))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a111d">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(url)}">
{'<meta name="robots" content="noindex, follow">' if noindex else ''}
<meta property="og:site_name" content="Hudson Happens">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(img)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,700;1,9..144,500&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles.css">
{ld}</head>
<body>
{HEADER}
<main id="main" tabindex="-1">
{body}
</main>
{footer()}
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script src="/static.js" defer></script>
</body>
</html>
"""


def crumbs(items):
    """items: [(label, path or None)]; returns (html, BreadcrumbList JSON-LD)."""
    h = '<nav class="crumbs" aria-label="Breadcrumb"><ol>' + "".join(
        f'<li><a href="{p}">{esc(l)}</a></li>' if p else f'<li aria-current="page">{esc(l)}</li>' for l, p in items) + "</ol></nav>"
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": l, **({"item": BASE + p} if p else {})} for i, (l, p) in enumerate(items)]}
    return h, ld


def row(e):
    c = CITY_BY_NAME.get(e["city"], {})
    p = price_text(e)
    thumb = f'<img src="{esc(e["image"])}" alt="" loading="lazy" onerror="this.remove()">' if e.get("image") else ""
    return f"""<li class="row"><a class="row-main" href="{e['path']}">
  <span class="thumb">{thumb}</span>
  <span class="row-text"><span class="row-title">{esc(e['title'])}{'<span class="badge-free">FREE</span>' if e.get('free') else ''}</span>
  <span class="row-sub">{esc('All day' if e['all_day'] else fmt_time(e['_start']))}{' · ' + esc(venue_name(e.get('venue'))) if e.get('venue') else ''}<span class="city-tag {c.get('cls', '')}">{esc(e['city'])}</span></span></span>
</a>{f'<span class="row-price">{esc(p)}</span>' if p and p != 'Free' else ''}</li>"""


def day_groups(events, cap=LIST_CAP):
    seen, uniq = set(), []
    for e in events:
        k = (re.sub(r"\W+", "", e["title"].lower()), e["_day"] - dt.timedelta(days=e["_day"].weekday()))
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    events = uniq
    if not events:
        return '<p class="empty">Nothing on the calendar here right now. <a href="/" style="color:var(--accent)">See everything coming up →</a></p>'
    groups = defaultdict(list)
    for e in events[:cap]:
        groups[e["_day"]].append(e)
    out = "".join(f'<section class="day"><h2 class="day-h">{esc(fmt_day_long(dt.datetime.combine(d, dt.time())))}</h2><ul class="rows">{"".join(row(e) for e in evs)}</ul></section>'
                  for d, evs in groups.items())
    if len(events) > cap:
        out += f'<p class="more-note">Showing the first {cap} of {len(events)}. <a href="/#/events">Browse and filter all events →</a></p>'
    return out


# ---------------------------------------------------------------- event pages
def event_jsonld(e):
    s = e["_start"]
    venue = venue_name(e.get("venue")) or e["city"]
    addr = {"@type": "PostalAddress", "addressLocality": e["city"], "addressRegion": "NJ", "addressCountry": "US"}
    street = (e.get("address") or "").split(",")[0].strip()
    if street and re.match(r"^\d", street):
        addr["streetAddress"] = street
    ld = {
        "@context": "https://schema.org", "@type": "Event",
        "name": e["title"],
        "startDate": s.date().isoformat() if e["all_day"] else s.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "Place", "name": venue, "address": addr},
        "description": (e.get("description") or summary(e))[:500],
        "url": BASE + e["path"],
    }
    if e.get("_end") and not e["all_day"]:
        ld["endDate"] = e["_end"].isoformat()
    if e.get("image"):
        ld["image"] = [e["image"]]
    p = price_text(e)
    if p == "Free":
        ld["isAccessibleForFree"] = True
        ld["offers"] = {"@type": "Offer", "price": 0, "priceCurrency": "USD", "url": e.get("url") or BASE + e["path"], "availability": "https://schema.org/InStock"}
    elif m := re.match(r"\$(\d+(?:\.\d+)?)", p or ""):
        ld["offers"] = {"@type": "Offer", "price": float(m.group(1)), "priceCurrency": "USD", "url": e.get("url") or BASE + e["path"], "availability": "https://schema.org/InStock"}
    return ld


def other_dates(e):
    occ = [x for x in e.get("_series", []) if x["id"] != e["id"]]
    if not occ:
        return ""
    links = "".join(f'<a class="chip" href="{x["path"]}">{esc(fmt_day_short(x["_start"]))}</a>' for x in occ[:12])
    more = f' <span style="color:var(--muted)">+{len(occ) - 12} more</span>' if len(occ) > 12 else ""
    return f'<h2 class="detail-sub">Other dates</h2><nav class="sublinks" aria-label="Other dates">{links}{more}</nav>'


def build_event(e, by_venue, by_city_day):
    s, c = e["_start"], CITY_BY_NAME.get(e["city"], {})
    time_str = "All day" if e["all_day"] else fmt_time(s) + (f" – {fmt_time(e['_end'])}" if e.get("_end") and e["_end"].date() == s.date() else "")
    venue = venue_name(e.get("venue"))
    vslug = e.get("_venue_slug")
    maps = "https://www.google.com/maps/search/?api=1&query=" + html.escape(re.sub(r"\s+", "+", ", ".join(x for x in [e.get("venue"), e.get("address"), e["city"], "NJ"] if x)), quote=True)
    p = price_text(e)
    cr, cr_ld = crumbs([("Home", "/"), (e["city"], f"/{c.get('slug', '')}/"), (e["title"], None)])
    same = {x["id"] for x in e.get("_series", [])}
    more_venue = [x for x in by_venue.get(vslug, []) if x["id"] not in same][:6] if vslug else []
    more_day = [x for x in by_city_day.get((e["city"], e["_day"]), []) if x["id"] != e["id"] and x not in more_venue][:6]
    lst = lambda evs: '<ul class="rows">' + "".join(row(x) for x in evs) + "</ul>"
    data = {"id": e["id"], "title": e["title"], "start": e["start"], "end": e.get("end"), "all_day": e["all_day"],
            "location": ", ".join(x for x in [e.get("venue"), e.get("address"), e["city"]] if x), "url": e.get("url") or "", "page": BASE + e["path"]}
    body = f"""<article class="wrap detail" style="max-width:900px">
  {cr}
  {f'<div class="detail-hero"><img src="{esc(e["image"])}" alt="" onerror="this.parentNode.remove()"></div>' if e.get('image') else ''}
  <p class="kicker" style="margin-top:22px">{esc(' · '.join(e['categories']))}</p>
  <h1>{esc(e['title'])}</h1>
  <p class="lede">{esc(summary(e))}</p>
  <div class="facts">
    <div class="fact"><div class="k">When</div><div class="v">{esc(fmt_day_long(s))}<br>{esc(time_str)}</div></div>
    <div class="fact"><div class="k">Where</div><div class="v">{f'<a href="/venues/{vslug}/">{esc(venue)}</a>' if vslug else esc(venue or e['city'])}{f'<br><span style="color:var(--muted)">{esc(e["address"])}</span>' if e.get('address') and e['address'] != e.get('venue') else ''}<br><a href="{maps}" target="_blank" rel="noopener">Open in Maps ↗</a></div></div>
    <div class="fact"><div class="k">Town</div><div class="v"><a class="city-tag {c.get('cls', '')}" href="/{c.get('slug', '')}/">{esc(e['city'])}</a></div></div>
    <div class="fact"><div class="k">Price</div><div class="v"{' style="color:var(--free)"' if p == 'Free' else ''}>{esc(p or 'See listing')}</div></div>
  </div>
  <div class="detail-actions">
    {f'<a class="btn primary" href="{esc(e["url"])}" target="_blank" rel="noopener nofollow">View on {esc(e["source"])} ↗</a>' if e.get('url') else ''}
    <button type="button" class="btn" data-act="cal">Add to calendar</button>
    <button type="button" class="btn" data-act="save" aria-pressed="false">♡ Save</button>
    <button type="button" class="btn" data-act="share">Share</button>
  </div>
  {f'<h2 class="detail-sub">About this event</h2><p class="detail-desc">{esc(e["description"])}</p>' if e.get('description') and len(e['description']) > 20 else ''}
  {other_dates(e)}
  <p class="source-note">Listing from {esc(e['source'])}. Details can change, so check the original before you go.</p>
  {f'<section class="related"><h2 class="detail-sub">More at <a href="/venues/{vslug}/">{esc(venue)}</a></h2>{lst(more_venue)}</section>' if more_venue else ''}
  {f'<section class="related"><h2 class="detail-sub">Also in {esc(e["city"])} on {esc(fmt_day_short(s))}</h2>{lst(more_day)}</section>' if more_day else ''}
  <script type="application/json" id="event-data">{ld_json(data)}</script>
</article>"""
    when = fmt_day_short(s) + ("" if e["all_day"] else f", {fmt_time(s)}")
    t = e["title"] if len(e["title"]) <= 60 else e["title"][:57].rstrip() + "…"
    return page(path=e["path"], title=f"{t} · {when} · {e['city']}", description=summary(e)[:300], body=body,
                jsonld=[event_jsonld(e), cr_ld], image=e.get("image"), noindex=e["_noindex"], og_type="article")


# ---------------------------------------------------------------- list pages
def build_list(path, h1, kicker, intro, events, title, description, crumb_items, links=None, noindex_if_empty=True):
    cr, cr_ld = crumbs(crumb_items)
    chips = "".join(f'<a class="chip" href="{p}">{esc(l)}</a>' for l, p in links or [])
    sub = f'<nav class="sublinks" aria-label="Related">{chips}</nav>' if links else ""
    body = f"""<div class="wrap" style="max-width:960px">
  {cr}
  <header class="page-head"><p class="kicker">{esc(kicker)}</p><h1 class="display">{h1}</h1>
  <p class="sub">{esc(intro)}</p></header>
  {sub}
  {day_groups(events)}
</div>"""
    item_ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": BASE + e["path"], "name": e["title"]} for i, e in enumerate(events[:50])]}
    return page(path=path, title=title, description=description, body=body, jsonld=[cr_ld, item_ld] if events else [cr_ld],
                noindex=noindex_if_empty and not events)


def count_phrase(n, what="events"):
    return f"{n} {what}" if n != 1 else f"1 {what[:-1]}"


# ---------------------------------------------------------------- main build
def build(events, generated=None):
    now = generated or dt.datetime.now(TZ)
    today = now.date()
    horizon = today + dt.timedelta(days=WINDOW_DAYS - 1)
    w0, w1 = weekend_range(today)

    evs = []
    for e in events:
        e = dict(e)
        e["_start"] = dt.datetime.fromisoformat(e["start"]).astimezone(TZ)
        e["_end"] = dt.datetime.fromisoformat(e["end"]).astimezone(TZ) if e.get("end") else None
        e["_day"] = e["_start"].date()
        e["_noindex"] = bool(NOINDEX.search(e["title"]) or NOINDEX.search(e.get("venue") or ""))
        e.setdefault("path", event_path(e, e["_start"]))
        vn = venue_name(e.get("venue"))
        e["_venue_slug"] = slugify(vn) if vn and not GENERIC_VENUE.match(vn) and not e["_noindex"] else None
        evs.append(e)
    evs.sort(key=lambda e: (e["_day"], not e["all_day"], e["_start"]))

    # Recurring events (same title at the same venue): only the next date goes in search;
    # later dates still get a page but are noindex, and link to the series' next date.
    series = defaultdict(list)
    for e in evs:
        series[(re.sub(r"\W+", "", e["title"].lower()), venue_name(e.get("venue")).lower())].append(e)
    for occ in series.values():
        for e in occ:
            e["_series"] = occ
        for e in occ[1:]:
            e["_noindex"] = True

    # Wipe previous output
    for name in GENERATED:
        p = SITE / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    by_venue, by_city_day = defaultdict(list), defaultdict(list)
    for e in evs:
        if e["_venue_slug"]:
            by_venue[e["_venue_slug"]].append(e)
        if not e["_noindex"]:
            by_city_day[(e["city"], e["_day"])].append(e)
    # Only venues with 2+ upcoming events get a page; don't link to the rest.
    for e in evs:
        if e["_venue_slug"] and sum(x["_day"] >= today for x in by_venue[e["_venue_slug"]]) < 2:
            e["_venue_slug"] = None

    sitemap = ["/"]
    written = 0

    def write(path, content, index=True):
        nonlocal written
        out = SITE / path.strip("/") / "index.html" if path.endswith("/") else SITE / path.lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        written += 1
        if index:
            sitemap.append(path)

    # Event pages
    for e in evs:
        write(e["path"], build_event(e, by_venue, by_city_day), index=not e["_noindex"])

    listable = [e for e in evs if not e["_noindex"] and not e["categories"] == ["Civic"] and not ADMIN.search(e["title"])]
    month = [e for e in listable if e["_day"] <= horizon]
    filters = {
        "": ("Things to do in {where}", "Everything on the calendar in {where} for the next 30 days, day by day.", lambda e: True),
        "tonight/": ("Things to do in {where} tonight", "What's on in {where} this evening, from 4pm on.", lambda e: e["_day"] == today and (e["all_day"] or e["_start"].hour >= 16)),
        "this-weekend/": ("Things to do in {where} this weekend", "Friday through Sunday in {where}: shows, markets, family events and nights out.", lambda e: w0 <= e["_day"] <= w1),
        "free/": ("Free things to do in {where}", "No cover, no tickets. Free events in {where} over the next 30 days.", lambda e: e.get("free")),
        "kids/": ("Things to do with kids in {where}", "Story times, family shows, classes and kid-friendly events in {where}.", lambda e: "Kids & Family" in e["categories"]),
        "live-music/": ("Live music in {where}", "Concerts, bands, DJs, jazz and open mics in {where} over the next 30 days.", lambda e: "Music" in e["categories"]),
    }
    labels = {"": "Everything", "tonight/": "Tonight", "this-weekend/": "This weekend", "free/": "Free", "kids/": "With kids", "live-music/": "Live music"}

    def scope_links(prefix):
        return [(labels[k], f"{prefix}{k}") for k in filters]

    for c in CITIES:
        in_city = [e for e in month if e["city"] == c["name"]]
        for key, (h, intro, f) in filters.items():
            lst = [e for e in in_city if f(e)]
            path = f"/{c['slug']}/{key}"
            heading = h.format(where=c["name"])
            kicker = f"{c['name']} · {count_phrase(len(lst))}"
            if key == "this-weekend/":
                kicker += f" · {fmt_day_short(dt.datetime.combine(w0, dt.time()))} – {fmt_day_short(dt.datetime.combine(w1, dt.time()))}"
            desc = f"{heading}: {count_phrase(len(lst))} on the calendar" + (f", including {lst[0]['title']}" if lst else "") + ". Updated three times a day."
            body_intro = (c["intro"] + " " if key == "" else "") + intro.format(where=c["name"])
            crumb = [("Home", "/"), (c["name"], f"/{c['slug']}/" if key else None)] + ([(labels[key], None)] if key else [])
            write(path, build_list(path, esc(heading).replace(esc(c["name"]), f'<span class="hl">{esc(c["name"])}</span>', 1), kicker, body_intro, lst,
                                   f"{heading} · Hudson Happens", desc[:300], crumb, scope_links(f"/{c['slug']}/")), index=bool(lst))

    where_all = "Jersey City, Hoboken & Bayonne"
    for key, (h, intro, f) in filters.items():
        if key == "":
            continue
        lst = [e for e in month if f(e)]
        path = f"/{key}"
        heading = h.format(where=where_all)
        city_links = [(f"{c['name']}", f"/{c['slug']}/{key}") for c in CITIES]
        desc = f"{heading}: {count_phrase(len(lst))}" + (f", including {lst[0]['title']}" if lst else "") + ". Updated three times a day."
        write(path, build_list(path, esc(heading), f"All three towns · {count_phrase(len(lst))}", intro.format(where=where_all), lst,
                               f"{heading} · Hudson Happens", desc[:300], [("Home", "/"), (labels[key], None)], city_links), index=bool(lst))

    # Venues
    venues = []
    for slug, vevs in by_venue.items():
        vevs = [e for e in vevs if e["_day"] >= today]
        if len(vevs) < 2:
            continue
        name = venue_name(vevs[0]["venue"])
        city = max(set(e["city"] for e in vevs), key=lambda x: sum(e["city"] == x for e in vevs))
        addr = next((e["address"] for e in vevs if e.get("address") and re.match(r"^\d", e["address"])), "")
        venues.append((slug, name, city, addr, vevs))
        path = f"/venues/{slug}/"
        c = CITY_BY_NAME[city]
        intro = f"Upcoming events at {name}{', ' + addr if addr else ''} in {city}. {count_phrase(len(vevs))} on the calendar."
        cr_items = [("Home", "/"), ("Venues", "/venues/"), (name, None)]
        place_ld = {"@context": "https://schema.org", "@type": "Place", "name": name, "url": BASE + path,
                    "address": {"@type": "PostalAddress", "addressLocality": city, "addressRegion": "NJ", "addressCountry": "US", **({"streetAddress": addr.split(",")[0]} if addr else {})}}
        html_page = build_list(path, f'<span class="hl">{esc(name)}</span>', f"Venue · {city}", intro, vevs,
                               f"{name} events · {city} · Hudson Happens", f"What's on at {name} in {city}, NJ: {count_phrase(len(vevs))} coming up, including {vevs[0]['title']}."[:300],
                               cr_items, [(f"More in {city}", f"/{c['slug']}/"), ("All venues", "/venues/")])
        html_page = html_page.replace("</head>", f'<script type="application/ld+json">{ld_json(place_ld)}</script>\n</head>', 1)
        write(path, html_page)

    cr, cr_ld = crumbs([("Home", "/"), ("Venues", None)])
    blocks = ""
    for c in CITIES:
        vs = sorted((v for v in venues if v[2] == c["name"]), key=lambda v: -len(v[4]))
        if vs:
            blocks += f'<section class="day"><h2 class="day-h"><a href="/{c["slug"]}/" style="text-decoration:none">{esc(c["name"])}</a></h2><ul class="venue-index">' + "".join(
                f'<li><a href="/venues/{s}/"><strong>{esc(n)}</strong><span>{count_phrase(len(v))} coming up</span></a></li>' for s, n, _, _, v in vs) + "</ul></section>"
    write("/venues/", page(path="/venues/", title="Venues in Jersey City, Hoboken & Bayonne · Hudson Happens",
                          description=f"{len(venues)} venues with events coming up across Jersey City, Hoboken and Bayonne: theaters, bars, libraries, galleries and more.",
                          body=f'<div class="wrap" style="max-width:960px">{cr}<header class="page-head"><p class="kicker">Venues</p><h1 class="display">Places around <span class="hl">town</span></h1><p class="sub">Every venue with two or more events coming up, by town.</p></header>{blocks}</div>',
                          jsonld=[cr_ld]))

    # 404 (expired event links land here)
    write("/404.html", page(path="/404.html", title="Page not found · Hudson Happens", description="This page isn't on the calendar anymore.", noindex=True,
        body='<div class="wrap" style="max-width:760px"><header class="page-head"><p class="kicker">Not found</p><h1 class="display">That one\'s <span class="hl">already happened</span></h1>'
             '<p class="sub">Events come off the calendar once they\'re over. Here\'s what\'s coming up instead.</p></header>'
             '<nav class="sublinks" aria-label="Browse">' + "".join(f'<a class="chip" href="/{c["slug"]}/">Things to do in {esc(c["name"])}</a>' for c in CITIES)
             + '<a class="chip" href="/this-weekend/">This weekend</a><a class="chip" href="/free/">Free events</a><a class="chip" href="/">Home</a></nav></div>'), index=False)

    # sitemap + robots
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in sitemap:
        sm.append(f"  <url><loc>{esc(BASE + p)}</loc></url>")
    sm.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sm) + "\n")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    print(f"built {written} pages, {len(sitemap)} in sitemap ({len(venues)} venues)", file=sys.stderr)
    return written


def main():
    d = json.loads(DATA.read_text())
    assign_paths(d["events"])
    DATA.write_text(json.dumps(d, indent=1))
    gen = dt.datetime.fromisoformat(d["generated"]).astimezone(TZ) if d.get("generated") else None
    # Build "today" from the real clock so weekend/tonight pages stay correct between refreshes.
    build(d["events"], max(gen, dt.datetime.now(TZ)) if gen else None)


if __name__ == "__main__":
    main()
