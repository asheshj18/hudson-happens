(() => {
  "use strict";
  const TZ = "America/New_York";
  const CITIES = [
    { name: "Jersey City", slug: "jersey-city", cls: "jc", blurb: "Downtown, the Heights, Journal Square" },
    { name: "Hoboken", slug: "hoboken", cls: "hob", blurb: "Mile square, one PATH stop away" },
    { name: "Bayonne", slug: "bayonne", cls: "bay", blurb: "The peninsula, on the Kill van Kull" },
  ];
  const CITY_BY_NAME = Object.fromEntries(CITIES.map((c) => [c.name, c]));
  const CITY_BY_SLUG = Object.fromEntries(CITIES.map((c) => [c.slug, c]));
  const PAGE = 40;
  const app = document.getElementById("app");

  let events = [];
  let byId = new Map();
  let venues = [];
  let generated = null;
  const saved = new Set(JSON.parse(localStorage.getItem("hh:saved") || localStorage.getItem("hi:saved") || "[]"));

  // ---------------------------------------------------------------- utils
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const slugify = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/[\s_-]+/g, "-");
  const dayKey = (d) => d.toLocaleDateString("en-CA", { timeZone: TZ });
  const nyHour = (d) => +d.toLocaleString("en-US", { timeZone: TZ, hour: "numeric", hour12: false }) % 24;
  const addDays = (key, n) => { const d = new Date(key + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const dow = (key) => new Date(key + "T12:00:00Z").getUTCDay();
  const today = () => dayKey(new Date());
  const fmtTime = (d) => d.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
  const fmtDayLong = (key) => new Date(key + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", weekday: "long", month: "long", day: "numeric" });
  const fmtDayShort = (key) => new Date(key + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", weekday: "short", month: "short", day: "numeric" });
  const dayChipLabel = (key) => { const d = new Date(key + "T12:00:00Z"); return d.toLocaleDateString("en-US", { timeZone: "UTC", weekday: "short" }) + " " + d.getUTCDate(); };
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const when = (e) => `${fmtDayShort(e._day)} · ${e.all_day ? "All day" : fmtTime(e._start)}`;

  function weekendRange() {
    const t = today(), d = dow(t);
    if (d === 0) return [t, t];
    if (d === 6) return [t, addDays(t, 1)];
    return [d === 5 ? t : addDays(t, 5 - d), addDays(t, 7 - d)];
  }
  const isTonight = (e) => e._day === today() && !e.all_day && nyHour(e._start) >= 16 && !e.categories.includes("Civic");
  const isWeekend = (e) => { const [a, b] = weekendRange(); return e._day >= a && e._day <= b; };
  const WINDOW_DAYS = 30;
  const inWindow = (e) => e._day >= today() && e._day <= addDays(today(), WINDOW_DAYS - 1);
  // Date-range presets shared by the home page and the events page.
  const RANGES = {
    week: ["Next 7 days", 0, 6],
    nextweek: ["Next week", 7, 13],
    later: ["Later this month", 14, WINDOW_DAYS - 1],
    month: ["Next 30 days", 0, WINDOW_DAYS - 1],
  };
  const inRange = (e, key) => { const r = RANGES[key]; return !!r && e._day >= addDays(today(), r[1]) && e._day <= addDays(today(), r[2]); };

  // ---------------------------------------------------------------- icons
  const ICON_CAL = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4M12 13v5M9.5 15.5h5"/></svg>`;
  const ICON_HEART = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
  const ICON_SHARE = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6M8.2 13.2l7.6 3.6"/></svg>`;
  const ICON_SEARCH = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m20 20-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
  const ICON_DICE = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="15" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><circle cx="9" cy="15" r="1" fill="currentColor"/></svg>`;

  const calBtn = (e) => `<button type="button" class="icon-btn" data-act="cal" data-id="${esc(e.id)}" aria-label="Add ${esc(e.title)} to calendar" title="Add to calendar">${ICON_CAL}</button>`;
  const heartBtn = (e) => `<button type="button" class="icon-btn heart" data-act="save" data-id="${esc(e.id)}" aria-pressed="${saved.has(e.id)}" aria-label="Save ${esc(e.title)}" title="Save">${ICON_HEART}</button>`;
  const href = (e) => `#/event/${encodeURIComponent(e.id)}`;
  const priceText = (e) => (e.free ? "Free" : e.price && e.price !== "Paid" ? e.price : "");

  // ---------------------------------------------------------------- components
  function row(e) {
    const c = CITY_BY_NAME[e.city];
    return `<li class="row">
      <a class="row-main" href="${href(e)}">
        <span class="thumb">${e.image ? `<img src="${esc(e.image)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</span>
        <span class="row-text">
          <span class="row-title">${esc(e.title)}${e.free ? `<span class="badge-free">FREE</span>` : ""}</span>
          <span class="row-sub">${esc(e.all_day ? "All day" : fmtTime(e._start))}${e.venue ? ` · ${esc(e.venue)}` : ""}<span class="city-tag ${c?.cls || ""}">${esc(e.city)}</span></span>
        </span>
      </a>
      ${!e.free && priceText(e) ? `<span class="row-price">${esc(priceText(e))}</span>` : ""}
      ${calBtn(e)}${heartBtn(e)}
    </li>`;
  }

  function tile(e, pick) {
    const p = priceText(e);
    const d = new Date(e._day + "T12:00:00Z");
    const stamp = `<span class="stamp" aria-hidden="true"><b>${d.toLocaleDateString("en-US", { timeZone: "UTC", weekday: "short" }).toUpperCase()}</b><strong>${d.getUTCDate()}</strong><i>${d.toLocaleDateString("en-US", { timeZone: "UTC", month: "short" }).toUpperCase()}</i></span>`;
    return `<li class="tile${pick ? " pick" : ""}">
      <a class="tile-link" href="${href(e)}">
        ${stamp}
        <span class="tile-body">
          <span class="tile-top"><span class="tile-cat">${esc(e.categories[0])}</span>${p ? `<span class="tile-price${e.free ? " free" : ""}">${esc(p)}</span>` : ""}</span>
          <span class="tile-title">${esc(e.title)}</span>
          <span class="tile-when">${esc(e.all_day ? "All day" : fmtTime(e._start))}</span>
          <span class="tile-where">${esc(e.venue || e.city)}</span>
        </span>
      </a>
      ${calBtn(e)}
    </li>`;
  }

  function card(e) {
    const c = CITY_BY_NAME[e.city];
    return `<li class="card">
      <a class="card-link" href="${href(e)}">
        <span class="media">${e.image ? `<img src="${esc(e.image)}" alt="" loading="lazy" onerror="this.remove()">` : ""}<span class="ph" aria-hidden="true">${esc(c?.cls === "hob" ? "Hoboken" : c?.cls === "bay" ? "Bayonne" : "JC")}</span></span>
        <span class="body">
          <span class="cat">${esc(e.categories[0])}</span>
          <span class="ttl">${esc(e.title)}${e.free ? `<span class="badge-free">FREE</span>` : ""}</span>
          <span class="meta">${esc(when(e))}${e.venue ? ` · ${esc(e.venue)}` : ""}</span>
          <span class="meta"><span class="city-tag ${c?.cls || ""}">${esc(e.city)}</span></span>
        </span>
      </a>
      <span class="acts">${heartBtn(e)}${calBtn(e)}</span>
    </li>`;
  }

  function dayGroups(list, { perDay = Infinity, moreHref } = {}) {
    if (!list.length) return `<p class="empty">Nothing here right now. Try another filter.</p>`;
    const groups = new Map();
    for (const e of list) (groups.get(e._day) || groups.set(e._day, []).get(e._day)).push(e);
    const t = today();
    let html = "";
    for (const [k, evs] of groups) {
      const label = k === t ? "Today" : k === addDays(t, 1) ? "Tomorrow" : fmtDayLong(k);
      const shown = evs.slice(0, perDay);
      html += `<section class="day" aria-label="${esc(label)}"><h2 class="day-h">${esc(label)}${k <= addDays(t, 1) ? `<small>${esc(fmtDayLong(k))}</small>` : ""}</h2><ul class="rows">${shown.map(row).join("")}</ul>`;
      if (evs.length > shown.length) html += `<a class="more-link" href="${moreHref ? moreHref(k) : `#/events?day=${k}`}">+ ${evs.length - shown.length} more on ${esc(new Date(k + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", weekday: "long" }))}</a>`;
      html += `</section>`;
    }
    return html;
  }

  function shelf(title, list, viewAll, { picks = false } = {}) {
    if (!list.length) return "";
    return `<section class="shelf">
      <div class="shelf-head"><h2 class="shelf-title">${title}</h2>${viewAll ? `<a class="view-all" href="${viewAll}">View all →</a>` : ""}</div>
      <div class="shelf-wrap"><ul class="tiles">${list.map((e) => tile(e, picks)).join("")}</ul>
      <button type="button" class="shelf-next" data-act="scroll" aria-label="Scroll ${esc(title.replace(/<[^>]+>/g, ""))} right">›</button></div>
    </section>`;
  }

  // ---------------------------------------------------------------- picks
  // "Local picks": upcoming, has an image, not civic/library-admin, spread across cities and categories.
  function insiderPicks(n = 10) {
    const pool = events.filter((e) => e._day <= addDays(today(), 14) && !e.categories.includes("Civic") && !/board of trustees|registration|drop-in|book a librarian/i.test(e.title));
    const score = (e) => (e.image ? 3 : 0) + (e.source === "Ticketmaster" || e.source === "Eventbrite" || e.source === "Luma" ? 3 : 0) + (nyHour(e._start) >= 17 ? 1 : 0) - (e.categories.includes("Kids & Family") ? 1 : 0);
    const sorted = pool.slice().sort((a, b) => score(b) - score(a) || a._start - b._start);
    const out = [], seenCat = {}, seenTitle = new Set();
    for (const e of sorted) {
      const key = e.title.toLowerCase();
      if (seenTitle.has(key)) continue;
      if ((seenCat[e.categories[0]] || 0) >= 2) continue;
      out.push(e); seenTitle.add(key); seenCat[e.categories[0]] = (seenCat[e.categories[0]] || 0) + 1;
      if (out.length >= n) break;
    }
    return out.sort((a, b) => a._start - b._start);
  }
  const uniqueTitles = (list, n) => { const s = new Set(); return list.filter((e) => !s.has(e.title.toLowerCase()) && s.add(e.title.toLowerCase())).slice(0, n); };

  // ---------------------------------------------------------------- views
  function viewHome() {
    const upcoming = events.filter((e) => e._day >= today());
    const added = events.length;
    const month = upcoming.filter(inWindow);
    const week = month.filter((e) => inRange(e, "week"));
    const t = today();
    const dayChips = [["all", "All 30 days"], ["today", "Today"], [addDays(t, 1), "Tomorrow"], ["weekend", "This weekend"], ["week", "Next 7 days"], ["nextweek", "Next week"], ["later", "Later this month"]];
    const sel = state.homeDay || "all";
    const monthList = month.filter((e) => sel === "all" || (sel === "today" ? e._day === t : sel === "weekend" ? isWeekend(e) : RANGES[sel] ? inRange(e, sel) : e._day === sel));
    const counts = Object.fromEntries(CITIES.map((c) => [c.name, upcoming.filter((e) => e.city === c.name).length]));

    return `<div class="wrap">
      <section class="hero">
        <p class="kicker">${added.toLocaleString()} things on the calendar · Jersey City · Hoboken · Bayonne</p>
        <h1 class="display">What's happening on <span class="hl">our side of the river.</span></h1>
        <div class="wave" aria-hidden="true"></div>
        <form class="hero-search" role="search" data-search>
          ${ICON_SEARCH}<label class="sr-only" for="hero-q">Search events, venues, neighborhoods</label>
          <input id="hero-q" name="q" type="search" placeholder="Try “farmers market”, “jazz” or “Grove St”…" autocomplete="off">
        </form>
        <div class="chips">
          <a class="chip" href="#/tonight">Tonight</a>
          <a class="chip" href="#/weekend">This weekend</a>
          <a class="chip" href="#/free">Free</a>
          <a class="chip" href="#/events?cat=Kids%20%26%20Family">With the kids</a>
          <a class="chip gold-outline" href="#/spontaneous">Surprise me</a>
        </div>
      </section>

      <div class="cities">
        ${CITIES.map((c) => `<a class="city-card ${c.cls}" href="#/events?city=${c.slug}"><strong>${esc(c.name)}</strong><span>${plural(counts[c.name], "event")} · ${esc(c.blurb)}</span></a>`).join("")}
      </div>

      ${shelf(`Worth the <span class="hl">trip</span>`, insiderPicks(), "#/events", { picks: true })}
      ${shelf(`<span class="hl green">Free</span> this month`, uniqueTitles(month.filter((e) => e.free && !e.categories.includes("Civic")), 14), "#/free")}
      ${shelf(`Tonight, <span class="hl">after work</span>`, uniqueTitles(upcoming.filter(isTonight), 14), "#/tonight")}
      ${shelf(`Bring <span class="hl">the kids</span>`, uniqueTitles(month.filter((e) => e.categories.includes("Kids & Family")), 14), "#/events?cat=Kids%20%26%20Family")}

      <p class="section-kicker">Shortcuts</p>
      <h2 class="display section-title">Know what you're after?</h2>
      <div class="guides">
        ${[
          ["Tonight", "What's on after 4. No morning story times.", "#/tonight"],
          ["This weekend", "Friday through Sunday, already sorted.", "#/weekend"],
          ["Free", "No cover, no tickets. Only events marked free.", "#/free"],
          ["Venues", "Every place on the calendar, by city.", "#/venues"],
          ["Learn something", "Classes, workshops, ESL and talks.", "#/events?cat=Learning"],
          ["Get moving", "Yoga, runs, tai chi and wellness.", "#/events?cat=Fitness%20%26%20Wellness"],
        ].map(([h, p, l]) => `<a class="guide" href="${l}"><h3>${h}</h3><p>${p}</p><span class="open-link">Take me there →</span></a>`).join("")}
      </div>

      <section class="spont-banner">
        <div><p class="kicker" style="margin-bottom:6px">Bored?</p><h2>Let us pick something for the next few hours</h2><p>One real event, close by. Not feeling it? Roll again.</p></div>
        <a class="btn primary" href="#/spontaneous">Surprise me</a>
      </section>

      <section style="margin-top:56px">
        <h2 class="display section-title" style="margin-bottom:6px">The month ahead</h2>
        <p style="color:var(--muted);margin:0 0 16px">The next 30 days, day by day. Plenty of time to plan.</p>
        <div class="chips" role="group" aria-label="Pick a day">
          ${dayChips.map(([v, l]) => `<button type="button" class="chip" data-act="homeday" data-day="${v}" aria-current="${sel === v}">${esc(l)}</button>`).join("")}
        </div>
        ${dayGroups(monthList, { perDay: sel === "all" ? 5 : 8 })}
      </section>
    </div>`;
  }

  // Events listing with sidebar (also powers Tonight / Weekend / Free presets)
  function filterEvents(q) {
    return events.filter((e) => {
      if (q.city && e.city !== CITY_BY_SLUG[q.city]?.name) return false;
      if (q.cat && !e.categories.includes(q.cat)) return false;
      if (q.free && !e.free) return false;
      if (q.preset === "tonight" && !isTonight(e)) return false;
      if (q.preset === "weekend" && !isWeekend(e)) return false;
      if (q.day === "today" && e._day !== today()) return false;
      if (q.day === "tomorrow" && e._day !== addDays(today(), 1)) return false;
      if (q.day && /^\d{4}-/.test(q.day) && e._day !== q.day) return false;
      if (q.day && RANGES[q.day] && !inRange(e, q.day)) return false;
      if (q.venue && slugify(e.venue) !== q.venue) return false;
      if (q.q && !e._text.includes(q.q.toLowerCase())) return false;
      return true;
    });
  }

  function qs(base, params) {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) u.set(k, v);
    const s = u.toString();
    return `#/${base}${s ? "?" + s : ""}`;
  }

  function viewEvents(route, q) {
    const preset = { tonight: "tonight", weekend: "weekend", free: "free" }[route] || null;
    const base = preset || "events";
    const fq = { ...q, preset, free: q.free || preset === "free" ? "1" : "" };
    const list = filterEvents(fq);
    const titles = {
      tonight: [`Tonight in <span class="hl">Hudson</span>`, "Shows and nights out starting at 4pm or later. Morning listings and meetings stay off this list."],
      weekend: [`This <span class="hl">weekend</span>`, `${fmtDayShort(weekendRange()[0])} – ${fmtDayShort(weekendRange()[1])}, already sorted.`],
      free: [`<span style="color:var(--free)">Free</span> things to do`, "No cover, no tickets. Only listings marked free."],
    };
    const [h1, sub] = titles[preset] || [q.q ? `Results for “${esc(q.q)}”` : `Things to do in <span class="hl">Hudson</span>`, ""];

    const keep = { ...q };
    const link = (patch) => qs(base, { ...keep, ...patch });
    const countFor = (patch) => filterEvents({ ...fq, ...patch }).length;

    const cityItems = [["", "All", "", countFor({ city: "" })], ...CITIES.map((c) => [c.slug, c.name, c.cls, countFor({ city: c.slug })])];
    const allCats = [...new Set(events.flatMap((e) => e.categories))];
    const catItems = allCats.map((c) => [c, countFor({ cat: c })]).filter(([c, n]) => n > 0 || q.cat === c).sort((a, b) => b[1] - a[1]);
    const t = today();
    const dayOpts = preset === "tonight" || preset === "weekend" ? [] : [["", "All dates"], ["today", "Today"], ["tomorrow", "Tomorrow"], ...[2, 3, 4, 5, 6].map((i) => [addDays(t, i), dayChipLabel(addDays(t, i))]), ...["week", "nextweek", "later", "month"].map((k) => [k, RANGES[k][0]])];
    const shown = list.slice(0, state.shown);
    const view = q.view === "grid" ? "grid" : "list";

    const active = [];
    if (q.q) active.push([`“${q.q}”`, link({ q: "" })]);
    if (q.venue) active.push([list[0]?.venue || venues.find((v) => v.slug === q.venue)?.name || q.venue, link({ venue: "" })]);

    let body;
    if (view === "grid") {
      body = list.length ? `<ul class="grid">${shown.map(card).join("")}</ul>` : `<p class="empty">Nothing matches. Try another filter.</p>`;
    } else {
      body = dayGroups(shown);
    }
    if (list.length > state.shown) body += `<button type="button" class="btn show-more" data-act="more">Show more (${list.length - state.shown} left)</button>`;

    return `<div class="wrap layout">
      <details class="sidebar" ${window.innerWidth > 800 ? "open" : ""}>
        <summary>Filters</summary>
        <h2 class="side-h">City</h2>
        <ul class="side-list">${cityItems.map(([slug, name, cls, n]) => `<li><a href="${link({ city: slug })}" aria-current="${(q.city || "") === slug}"><span class="dot ${cls}"></span>${esc(name)}<span class="n">${n}</span></a></li>`).join("")}</ul>
        <h2 class="side-h">Events</h2>
        <ul class="side-list">
          <li><a href="${link({ cat: "" })}" aria-current="${!q.cat}"><span class="dot"></span>All<span class="n">${countFor({ cat: "" })}</span></a></li>
          ${catItems.map(([c, n]) => `<li><a href="${link({ cat: c })}" aria-current="${q.cat === c}"><span class="dot"></span>${esc(c)}<span class="n">${n}</span></a></li>`).join("")}
          ${preset === "free" ? "" : `<li><a href="${link({ free: q.free ? "" : "1" })}" aria-current="${!!q.free}"><span class="dot free"></span>Free only<span class="n">${countFor({ free: "1" })}</span></a></li>`}
        </ul>
      </details>

      <div>
        <div class="results-head">
          <div><h1 class="display">${h1}</h1>${sub ? `<p style="color:var(--muted);margin:10px 0 0">${sub}</p>` : ""}</div>
          <span class="count">${plural(list.length, "upcoming event")}</span>
        </div>
        ${dayOpts.length ? `<div class="toolbar chips" role="group" aria-label="Date">${dayOpts.map(([v, l]) => `<a class="chip sq" href="${link({ day: v })}" aria-current="${(q.day || "") === v}">${esc(l)}</a>`).join("")}</div>` : ""}
        <div class="toolbar">
          <div class="seg" role="group" aria-label="Layout">
            <a href="${link({ view: "" })}" aria-current="${view === "list"}">☰ List</a>
            <a href="${link({ view: "grid" })}" aria-current="${view === "grid"}">▦ Cards</a>
          </div>
          ${active.length ? `<div class="active-filters">${active.map(([l, h]) => `<a href="${h}" aria-label="Remove filter ${esc(l)}">${esc(l)}</a>`).join("")}</div>` : ""}
        </div>
        ${body}
      </div>
    </div>`;
  }

  function buildVenues() {
    const m = new Map();
    for (const e of events) {
      if (!e.venue || e.venue === e.city || /\b(zoom|virtual(ly)?|online|offsite|tbd)\b/i.test(e.venue)) continue;
      const slug = slugify(e.venue);
      if (!m.has(slug)) m.set(slug, { slug, name: e.venue, city: e.city, events: [], cats: {} });
      const v = m.get(slug);
      v.events.push(e);
      for (const c of e.categories) v.cats[c] = (v.cats[c] || 0) + 1;
    }
    venues = [...m.values()].map((v) => ({ ...v, count: v.events.length, top: Object.entries(v.cats).sort((a, b) => b[1] - a[1])[0]?.[0] || "", next: v.events[0] }));
  }

  function viewVenues(q) {
    const t = today();
    let list = venues.filter((v) => (!q.city || v.city === CITY_BY_SLUG[q.city]?.name) && (!q.known || v.top === q.known) && (!q.q || v.name.toLowerCase().includes(q.q.toLowerCase())));
    if (q.when === "tonight") list = list.filter((v) => v.events.some(isTonight));
    if (q.when === "weekend") list = list.filter((v) => v.events.some(isWeekend));
    list.sort(q.sort === "az" ? (a, b) => a.name.localeCompare(b.name) : q.sort === "soonest" ? (a, b) => a.next._start - b.next._start : (a, b) => b.count - a.count);
    const link = (patch) => qs("venues", { ...q, ...patch });
    const known = Object.entries(venues.reduce((acc, v) => ((acc[v.top] = (acc[v.top] || 0) + 1), acc), {})).sort((a, b) => b[1] - a[1]);

    return `<div class="wrap narrow" style="max-width:900px">
      <header class="page-head"><p class="kicker" style="color:var(--muted)">Venues</p><h1 class="display">Places <span class="hl">around town</span></h1>
      <p class="sub">Every place below has an upcoming public event. Filter by city or what a place is known for.</p></header>
      <form class="venue-tools" data-venue-search>
        <label class="field">${ICON_SEARCH}<span class="sr-only">Find a venue by name</span><input name="vq" type="search" value="${esc(q.q || "")}" placeholder="Find a venue by name" autocomplete="off"></label>
        <label class="sr-only" for="vsort">Sort</label>
        <select id="vsort" data-act="vsort">
          <option value="" ${!q.sort ? "selected" : ""}>Most events</option>
          <option value="soonest" ${q.sort === "soonest" ? "selected" : ""}>Soonest</option>
          <option value="az" ${q.sort === "az" ? "selected" : ""}>A–Z</option>
        </select>
      </form>
      <div class="filter-row"><span class="lbl">City</span><div class="chips">${CITIES.map((c) => `<a class="chip" href="${link({ city: q.city === c.slug ? "" : c.slug })}" aria-current="${q.city === c.slug}">${esc(c.name)} <span class="n">${venues.filter((v) => v.city === c.name).length}</span></a>`).join("")}</div></div>
      <div class="filter-row"><span class="lbl">Known for</span><div class="chips">${known.map(([k, n]) => `<a class="chip" href="${link({ known: q.known === k ? "" : k })}" aria-current="${q.known === k}">${esc(k)} <span class="n">${n}</span></a>`).join("")}</div></div>
      <div class="filter-row"><span class="lbl">When</span><div class="chips">
        <a class="chip" href="${link({ when: q.when === "tonight" ? "" : "tonight" })}" aria-current="${q.when === "tonight"}">On tonight <span class="n">${venues.filter((v) => v.events.some(isTonight)).length}</span></a>
        <a class="chip" href="${link({ when: q.when === "weekend" ? "" : "weekend" })}" aria-current="${q.when === "weekend"}">This weekend <span class="n">${venues.filter((v) => v.events.some(isWeekend)).length}</span></a>
        <span style="color:var(--muted);font-size:14px;align-self:center;padding-left:6px">${plural(list.length, "venue")}</span></div></div>
      <ul class="venue-list">${list.map((v) => `<li><a href="#/events?venue=${v.slug}"><span><strong>${esc(v.name)}</strong><span class="vmeta"><span class="city-tag ${CITY_BY_NAME[v.city]?.cls || ""}">${esc(v.city)}</span> · ${esc(v.top)} · Next ${esc(v.next._day === t ? "today" : fmtDayShort(v.next._day))}</span></span><span class="vcount">${plural(v.count, "event")}</span></a></li>`).join("") || `<li class="empty">No venues match.</li>`}</ul>
    </div>`;
  }

  function spontaneousPool() {
    const now = new Date(), soon = new Date(now.getTime() + 5 * 3600e3);
    const ok = (e) => !e.all_day && !e.categories.includes("Civic") && !/registration|drop-in|book a librarian|board of trustees/i.test(e.title);
    let pool = events.filter((e) => ok(e) && e._start >= new Date(now.getTime() - 30 * 60e3) && e._start <= soon);
    if (pool.length < 3) pool = events.filter((e) => ok(e) && e._day === today() && (e._end || e._start) >= now);
    if (pool.length < 3) pool = events.filter((e) => ok(e) && e._day <= addDays(today(), 1) && e._start >= now);
    return pool;
  }

  function viewSpontaneous() {
    const pool = spontaneousPool();
    if (!pool.length) return `<div class="wrap narrow"><header class="page-head"><h1 class="display" style="font-size:40px">Surprise me</h1></header><p class="empty">Nothing coming up in the next few hours. <a href="#/events?day=tomorrow" style="color:var(--accent)">See tomorrow →</a></p></div>`;
    if (state.spontIdx == null || state.spontIdx >= pool.length) state.spontIdx = Math.floor(Math.random() * pool.length);
    const e = pool[state.spontIdx];
    const c = CITY_BY_NAME[e.city];
    const p = priceText(e);
    return `<div class="wrap narrow">
      <header class="page-head"><h1 class="display" style="font-size:40px">Surprise me</h1>
      <p class="sub">One thing worth leaving the house for, happening in the next few hours. Don't like it? Roll again.</p></header>
      <article class="spont-card" aria-live="polite">
        <div class="top"><span class="tile-cat">${esc(e.categories[0])}</span>${p ? `<span class="tile-price${e.free ? " free" : ""}">${esc(p)}</span>` : ""}</div>
        <h2>${esc(e.title)}</h2>
        <p class="meta">${esc(when(e))}${e.venue ? ` · ${esc(e.venue)}` : ""} · <span class="city-tag ${c?.cls || ""}">${esc(e.city)}</span></p>
        <div class="spont-actions"><a class="btn primary" href="${href(e)}">See details</a>${calBtn(e)}<button type="button" class="icon-btn" data-act="share" data-id="${esc(e.id)}" aria-label="Share" title="Share">${ICON_SHARE}</button></div>
      </article>
      <button type="button" class="btn another" data-act="reroll">${ICON_DICE} Show me another (${pool.length} coming up)</button>
    </div>`;
  }

  function viewSaved() {
    const list = events.filter((e) => saved.has(e.id));
    return `<div class="wrap" style="max-width:900px">
      <header class="page-head"><p class="kicker" style="color:var(--muted)">Saved</p><h1 class="display">Your <span class="hl">list</span></h1>
      <p class="sub">Saved on this device. Tap the heart on any event to add it.</p></header>
      ${list.length ? dayGroups(list) : `<p class="empty">Nothing saved yet. <a href="#/events" style="color:var(--accent)">Browse events →</a></p>`}
    </div>`;
  }

  function viewDetail(id) {
    const e = byId.get(id);
    if (!e) return `<div class="wrap"><p class="empty">That event has ended or was removed. <a href="#/events" style="color:var(--accent)">Browse events →</a></p></div>`;
    const c = CITY_BY_NAME[e.city];
    const timeStr = e.all_day ? "All day" : fmtTime(e._start) + (e._end ? ` – ${fmtTime(e._end)}` : "");
    const map = e.address || e.venue ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([e.venue, e.address, e.city, "NJ"].filter(Boolean).join(", "))}` : "";
    const more = events.filter((x) => x.id !== e.id && x.venue && x.venue === e.venue).slice(0, 12);
    return `<article class="wrap detail" style="max-width:900px">
      <a class="back" href="javascript:history.back()">← Back</a>
      ${e.image ? `<div class="detail-hero"><img src="${esc(e.image)}" alt="" onerror="this.parentNode.remove()"></div>` : ""}
      <p class="kicker" style="margin-top:22px">${esc(e.categories.join(" · "))}</p>
      <h1>${esc(e.title)}</h1>
      <div class="facts">
        <div class="fact"><div class="k">When</div><div class="v">${esc(fmtDayLong(e._day))}<br>${esc(timeStr)}</div></div>
        <div class="fact"><div class="k">Where</div><div class="v">${esc(e.venue || e.city)}${e.address && e.address !== e.venue ? `<br><span style="color:var(--muted)">${esc(e.address)}</span>` : ""}${map ? `<br><a href="${map}" target="_blank" rel="noopener">Open in Maps ↗</a>` : ""}</div></div>
        <div class="fact"><div class="k">City</div><div class="v"><span class="city-tag ${c?.cls || ""}">${esc(e.city)}</span></div></div>
        <div class="fact"><div class="k">Price</div><div class="v" style="${e.free ? "color:var(--free)" : ""}">${esc(priceText(e) || "See listing")}</div></div>
      </div>
      <div class="detail-actions">
        ${e.url ? `<a class="btn primary" href="${esc(e.url)}" target="_blank" rel="noopener">View on ${esc(e.source)} ↗</a>` : ""}
        <button type="button" class="btn" data-act="cal" data-id="${esc(e.id)}">${ICON_CAL} Add to calendar</button>
        <button type="button" class="btn" data-act="save" data-id="${esc(e.id)}" aria-pressed="${saved.has(e.id)}">${saved.has(e.id) ? "♥ Saved" : "♡ Save"}</button>
        <button type="button" class="btn" data-act="share" data-id="${esc(e.id)}">${ICON_SHARE} Share</button>
      </div>
      ${e.description ? `<p class="detail-desc">${esc(e.description)}</p>` : ""}
      <p class="source-note">Listing from ${esc(e.source)}. Details can change, so check the original before you go.</p>
      ${more.length ? shelf(`More at <span class="hl">${esc(e.venue)}</span>`, more, `#/events?venue=${slugify(e.venue)}`) : ""}
    </article>`;
  }

  function footer() {
    const cats = [...new Set(events.flatMap((e) => e.categories))].sort();
    const srcs = generated ? Object.entries(generated.sources).filter(([, n]) => typeof n === "number" && n > 0).map(([s]) => s.replace(/_/g, " ")) : [];
    return `
      <div><h4>Categories</h4><ul>${cats.map((c) => `<li><a href="#/events?cat=${encodeURIComponent(c)}">${esc(c)}</a></li>`).join("")}</ul></div>
      <div><h4>Cities</h4><ul>${CITIES.map((c) => `<li><a href="#/events?city=${c.slug}">${esc(c.name)}</a></li>`).join("")}</ul></div>
      <div><h4>Explore</h4><ul>
        <li><a href="#/events">All events</a></li><li><a href="#/venues">Venues</a></li><li><a href="#/tonight">Tonight</a></li>
        <li><a href="#/weekend">This weekend</a></li><li><a href="#/free" style="color:var(--free)">Free events</a></li>
        <li><a href="#/saved">Saved</a></li><li><a href="#/spontaneous">Surprise me</a></li></ul></div>
      <div><h4>Hudson Happens</h4>
        <p>Events across Jersey City, Hoboken and Bayonne in one calendar.</p>
        ${generated ? `<p>Updated ${esc(new Date(generated.generated).toLocaleString("en-US", { timeZone: TZ, dateStyle: "medium", timeStyle: "short" }))}</p>` : ""}
        ${srcs.length ? `<p>Sources: ${esc(srcs.join(", "))}</p>` : ""}
        <p>Details come from each organizer. Check the original listing before you go.</p></div>`;
  }

  // ---------------------------------------------------------------- routing
  const state = { shown: PAGE, homeDay: "all", spontIdx: null, lastRoute: "" };

  function parseHash() {
    const h = location.hash.replace(/^#\/?/, "");
    const [path, query = ""] = h.split("?");
    const parts = path.split("/").filter(Boolean);
    return { route: parts[0] || "home", arg: parts[1] ? decodeURIComponent(parts.slice(1).join("/")) : null, q: Object.fromEntries(new URLSearchParams(query)) };
  }

  function render() {
    const { route, arg, q } = parseHash();
    const key = route + "|" + JSON.stringify({ ...q, view: undefined });
    if (key !== state.lastRoute) { state.shown = PAGE; if (route !== "spontaneous") state.spontIdx = null; }
    const routeChanged = route + arg !== state.lastRoute.split("|")[0] + (state.lastArg || "");
    state.lastRoute = key; state.lastArg = arg;

    let html;
    if (route === "events" || route === "tonight" || route === "weekend" || route === "free") html = viewEvents(route, q);
    else if (route === "venues") html = viewVenues(q);
    else if (route === "spontaneous") html = viewSpontaneous();
    else if (route === "saved") html = viewSaved();
    else if (route === "event") html = viewDetail(arg);
    else html = viewHome();
    app.innerHTML = html;

    document.querySelectorAll(".mainnav a").forEach((a) => (a.dataset.nav === route ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    const titles = { events: "Things to do", venues: "Venues", tonight: "Tonight", weekend: "This weekend", free: "Free events", saved: "Saved", spontaneous: "Surprise me" };
    document.title = route === "event" && byId.get(arg) ? `${byId.get(arg).title} · Hudson Happens` : `${titles[route] ? titles[route] + " · " : ""}Hudson Happens: what's on in Jersey City, Hoboken & Bayonne`;
    if (routeChanged) { window.scrollTo(0, 0); }
    updateSavedCount();
  }

  // ---------------------------------------------------------------- actions
  function toast(msg) { const t = document.getElementById("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2200); }
  function updateSavedCount() { document.getElementById("saved-count").textContent = saved.size || ""; }

  function icsFor(e) {
    const f = (d) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const icsEsc = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
    const end = e._end || new Date(e._start.getTime() + 2 * 3600e3);
    const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hudson Happens//EN", "BEGIN:VEVENT",
      `UID:${icsEsc(e.id)}@hudsonhappens.com`, `DTSTAMP:${f(new Date())}`,
      e.all_day ? `DTSTART;VALUE=DATE:${e._day.replace(/-/g, "")}` : `DTSTART:${f(e._start)}`,
      e.all_day ? `DTEND;VALUE=DATE:${addDays(e._day, 1).replace(/-/g, "")}` : `DTEND:${f(end)}`,
      `SUMMARY:${icsEsc(e.title)}`, `LOCATION:${icsEsc([e.venue, e.address, e.city].filter(Boolean).join(", "))}`,
      `DESCRIPTION:${icsEsc((e.description || "").slice(0, 500) + (e.url ? "\n\n" + e.url : ""))}`,
      e.url ? `URL:${e.url}` : "", "END:VEVENT", "END:VCALENDAR"].filter(Boolean);
    return lines.join("\r\n");
  }

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    const e = btn.dataset.id ? byId.get(btn.dataset.id) : null;
    if (act === "save" && e) {
      ev.preventDefault();
      saved.has(e.id) ? saved.delete(e.id) : saved.add(e.id);
      localStorage.setItem("hh:saved", JSON.stringify([...saved]));
      const on = saved.has(e.id);
      document.querySelectorAll(`[data-act="save"][data-id="${CSS.escape(e.id)}"]`).forEach((b) => { b.setAttribute("aria-pressed", on); if (b.classList.contains("btn")) b.textContent = on ? "♥ Saved" : "♡ Save"; });
      updateSavedCount();
      toast(on ? "Saved" : "Removed from saved");
      if (parseHash().route === "saved") render();
    } else if (act === "cal" && e) {
      ev.preventDefault();
      const blob = new Blob([icsFor(e)], { type: "text/calendar" });
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: slugify(e.title).slice(0, 60) + ".ics" });
      document.body.appendChild(a); a.click(); a.remove();
      toast("Calendar file downloaded");
    } else if (act === "share" && e) {
      const url = location.href.split("#")[0] + href(e);
      if (navigator.share) { try { await navigator.share({ title: e.title, url }); } catch {} }
      else { await navigator.clipboard?.writeText(url); toast("Link copied"); }
    } else if (act === "more") {
      state.shown += PAGE; const y = window.scrollY; render(); window.scrollTo(0, y);
    } else if (act === "homeday") {
      state.homeDay = btn.dataset.day; const y = window.scrollY; app.innerHTML = viewHome(); window.scrollTo(0, y);
    } else if (act === "reroll") {
      const n = spontaneousPool().length;
      if (n > 1) { let i; do { i = Math.floor(Math.random() * n); } while (i === state.spontIdx); state.spontIdx = i; }
      render();
    } else if (act === "scroll") {
      btn.previousElementSibling.scrollBy({ left: 520, behavior: "smooth" });
    }
  });

  document.addEventListener("submit", (ev) => {
    const f = ev.target;
    if (f.matches("[data-search]")) {
      ev.preventDefault();
      const v = f.q.value.trim();
      location.hash = qs("events", { q: v });
      f.q.blur();
    } else if (f.matches("[data-venue-search]")) {
      ev.preventDefault();
      location.hash = qs("venues", { ...parseHash().q, q: f.vq.value.trim() });
    }
  });
  let vt;
  document.addEventListener("input", (ev) => {
    if (ev.target.name === "vq") { clearTimeout(vt); const v = ev.target.value; vt = setTimeout(() => { history.replaceState(null, "", qs("venues", { ...parseHash().q, q: v.trim() })); render(); const i = document.querySelector('[name="vq"]'); i.focus(); i.setSelectionRange(v.length, v.length); }, 200); }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target.dataset.act === "vsort") location.hash = qs("venues", { ...parseHash().q, sort: ev.target.value });
  });
  window.addEventListener("hashchange", render);

  // ---------------------------------------------------------------- load
  fetch("data/events.json").then((r) => r.json()).then((data) => {
    generated = data;
    const now = new Date();
    events = data.events.map((e) => {
      const start = new Date(e.start);
      const end = e.end ? new Date(e.end) : null;
      return { ...e, _start: start, _end: end, _day: dayKey(start < now && end && end > now ? now : start),
        _text: [e.title, e.venue, e.description, e.city, e.address, ...e.categories].join(" ").toLowerCase() };
    }).filter((e) => (e._end || new Date(e._start.getTime() + 2 * 3600e3)) >= now)
      .sort((a, b) => a._day.localeCompare(b._day) || (a.all_day === b.all_day ? a._start - b._start : a.all_day ? -1 : 1));
    byId = new Map(events.map((e) => [e.id, e]));
    buildVenues();
    document.getElementById("footer").innerHTML = footer();
    render();
  }).catch((err) => {
    console.error(err);
    app.innerHTML = `<p class="empty">Couldn't load events. Run <code>python3 scripts/fetch_events.py</code> first.</p>`;
  });
})();
