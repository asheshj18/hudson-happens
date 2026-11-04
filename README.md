# Hudson Happens

Event listings for Jersey City, Hoboken and Bayonne in one place, filterable by date, city and category.

## Run locally

    python3 scripts/fetch_events.py      # pulls events -> site/data/events.json
    cd site && python3 -m http.server 8765
    open http://localhost:8765

No dependencies (Python 3.9+ standard library only).

## Data sources (all free tiers)

| Source | Type | Covers |
|---|---|---|
| City of Jersey City | iCal | Council and board meetings, outreach, town halls |
| Hoboken Public Library | Communico JSON | Library programs across all Hoboken branches |
| Bayonne Public Library | LibCal iCal | Library programs |
| Luma | Public discover API, filtered to the 3 cities | Tech, networking, wellness, social meetups |
| Ticketmaster | Discovery API (free key) | Concerts, comedy, theater, sports |
| Eventbrite | API (free token), per organizer in `eventbrite_organizers.txt` | Community events, classes, markets |
| SeatGeek | Platform API (free client ID) | Ticketed concerts, sports, theater |
| Google Events via SerpApi | API (free plan, 250 searches/mo) | Everything Google indexes: Facebook, Eventbrite, AllEvents, venue sites |
| Stevens Institute | iCal (performing arts + home games only) | Hoboken campus shows and sports |
| JC Families | iCal | Kids and family events in Jersey City |

### API keys
Copy `.env.example` to `.env` and fill in the keys. `.env` is gitignored. On GitHub, add the same names under Settings → Secrets → Actions.
- **Ticketmaster:** sign up at https://developer.ticketmaster.com, then use My Apps → Consumer Key → `TICKETMASTER_API_KEY`.
- **SeatGeek:** sign in at https://seatgeek.com/account/develop, create an app, then copy its Client ID → `SEATGEEK_CLIENT_ID`. The secret isn't needed.
- **SerpApi:** sign up at https://serpapi.com (free plan, no card), then copy the key from Dashboard → Api Key → `SERPAPI_KEY`. The fetcher spends at most 6 searches a run and caches results in `data/serpapi_cache.json` for 20 hours, so it uses about 180 searches a month. Set `SERPAPI_FORCE=1` to bypass the cache.
- **Eventbrite:** use https://www.eventbrite.com/platform/api-keys → Private token → `EVENTBRITE_TOKEN`. Then add organizer IDs to `eventbrite_organizers.txt`.

### Adding a source
Write a function in `scripts/fetch_events.py` that returns event dicts (see `from_ical` for the shape) and add it to `SOURCES`. If an organizer publishes an iCal feed, adding it takes one line with `from_ical(url, source, city)`.

## Search pages (SEO)
The app at `/` uses `#` routes, which search engines ignore. `scripts/build_pages.py` writes plain HTML pages next to it, with the content in the page itself, and `fetch_events.py` runs it after every refresh:

- `/events/<slug>/`: one page per event, with schema.org `Event` data. Repeat dates of a recurring event are `noindex` and link to each other.
- `/<town>/`, plus `/<town>/this-weekend/`, `tonight/`, `free/`, `kids/` and `live-music/`, and the same pages across all three towns (`/this-weekend/` etc.).
- `/venues/` and `/venues/<slug>/`, for venues with 2 or more upcoming events.
- `/sitemap.xml`, `/robots.txt` and `/404.html`.

These folders are regenerated every run, so don't edit them by hand. To rebuild from the current data without refetching, run `python3 scripts/build_pages.py`.

## Deploy
Cloudflare deploys the `site/` folder from GitHub on every push. `.github/workflows/refresh.yml` refreshes the data 3 times a day.

## Known gaps / next steps
- Hoboken city has no public event feed (only a RecDesk recreation calendar).
- The Jersey City Free Public Library blocks automated requests (HTTP 403).
- Categories come from keyword rules; an LLM pass would make them much better.
- Eventbrite only works if you list specific organizer IDs.
