# Hudson Happens

Event listings for Jersey City, Hoboken and Bayonne in one place, filterable by date, city and category.

## Run locally

    python3 scripts/fetch_events.py      # pulls events -> site/data/events.json
    cd site && python3 -m http.server 8765
    open http://localhost:8765

No dependencies (Python 3.9+ standard library only).

## Data sources (all free)

| Source | Type | Covers |
|---|---|---|
| City of Jersey City | iCal | Council and board meetings, outreach, town halls |
| Hoboken Public Library | Communico JSON | Library programs across all Hoboken branches |
| Bayonne Public Library | LibCal iCal | Library programs |
| Luma | Public discover API, filtered to the 3 cities | Tech, networking, wellness, social meetups |
| Ticketmaster | Discovery API (free key) | Concerts, comedy, theater, sports |
| Eventbrite | API (free token), per organizer in `eventbrite_organizers.txt` | Community events, classes, markets |

### API keys
Copy `.env.example` to `.env` and fill in the keys. `.env` is gitignored. On GitHub, add the same names under Settings → Secrets → Actions.
- **Ticketmaster:** sign up at https://developer.ticketmaster.com, then use My Apps → Consumer Key → `TICKETMASTER_API_KEY`.
- **Eventbrite:** use https://www.eventbrite.com/platform/api-keys → Private token → `EVENTBRITE_TOKEN`. Then add organizer IDs to `eventbrite_organizers.txt`.

### Adding a source
Write a function in `scripts/fetch_events.py` that returns event dicts (see `from_ical` for the shape) and add it to `SOURCES`. If an organizer publishes an iCal feed, adding it takes one line with `from_ical(url, source, city)`.

## Deploy
Push to GitHub, then point Netlify, Vercel or GitHub Pages at the `site/` folder. `.github/workflows/refresh.yml` refreshes the data 3 times a day.

## Known gaps / next steps
- Hoboken city has no public event feed (only a RecDesk recreation calendar).
- The Jersey City Free Public Library blocks automated requests (HTTP 403).
- Categories come from keyword rules; an LLM pass would make them much better.
- Eventbrite only works if you list specific organizer IDs.
