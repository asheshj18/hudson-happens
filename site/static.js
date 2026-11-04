// Small helper for the static (crawlable) pages: mobile menu, search, save, calendar, share.
// The full app lives at / (app.js); these pages just need to work without it.
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const toast = (msg) => { const t = $("#toast"); if (!t) return; t.textContent = msg; t.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2200); };

  // mobile menu
  const topbar = $(".topbar"), menuBtn = $(".menu-btn");
  if (topbar && menuBtn) {
    const setMenu = (open) => { topbar.classList.toggle("open", open); menuBtn.setAttribute("aria-expanded", String(open)); menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu"); };
    menuBtn.addEventListener("click", () => setMenu(!topbar.classList.contains("open")));
    document.addEventListener("click", (ev) => { if (topbar.classList.contains("open") && !topbar.contains(ev.target)) setMenu(false); });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && topbar.classList.contains("open")) { setMenu(false); menuBtn.focus(); } });
  }

  // search hands off to the app
  document.addEventListener("submit", (ev) => {
    const f = ev.target;
    if (!f.matches("[data-search]")) return;
    ev.preventDefault();
    const v = f.q.value.trim();
    location.href = "/#/events" + (v ? "?q=" + encodeURIComponent(v) : "");
  });

  // event page actions
  const dataEl = $("#event-data");
  if (!dataEl) return;
  const e = JSON.parse(dataEl.textContent);
  const saved = new Set(JSON.parse(localStorage.getItem("hh:saved") || "[]"));
  const saveBtn = $('[data-act="save"]');
  const paint = () => { const on = saved.has(e.id); saveBtn.setAttribute("aria-pressed", on); saveBtn.textContent = on ? "♥ Saved" : "♡ Save"; };
  if (saveBtn) paint();

  const ics = () => {
    const f = (d) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const x = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
    const start = new Date(e.start), end = e.end ? new Date(e.end) : new Date(start.getTime() + 2 * 3600e3);
    const day = e.start.slice(0, 10).replace(/-/g, "");
    const next = new Date(e.start.slice(0, 10) + "T12:00:00Z"); next.setUTCDate(next.getUTCDate() + 1);
    return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hudson Happens//EN", "BEGIN:VEVENT",
      `UID:${x(e.id)}@hudsonhappens.com`, `DTSTAMP:${f(new Date())}`,
      e.all_day ? `DTSTART;VALUE=DATE:${day}` : `DTSTART:${f(start)}`,
      e.all_day ? `DTEND;VALUE=DATE:${next.toISOString().slice(0, 10).replace(/-/g, "")}` : `DTEND:${f(end)}`,
      `SUMMARY:${x(e.title)}`, `LOCATION:${x(e.location)}`, `DESCRIPTION:${x(e.page)}`, `URL:${e.url || e.page}`,
      "END:VEVENT", "END:VCALENDAR"].join("\r\n");
  };

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "save") {
      saved.has(e.id) ? saved.delete(e.id) : saved.add(e.id);
      localStorage.setItem("hh:saved", JSON.stringify([...saved]));
      paint(); toast(saved.has(e.id) ? "Saved" : "Removed from saved");
    } else if (act === "cal") {
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([ics()], { type: "text/calendar" })), download: "event.ics" });
      document.body.appendChild(a); a.click(); a.remove(); toast("Calendar file downloaded");
    } else if (act === "share") {
      if (navigator.share) { try { await navigator.share({ title: e.title, url: e.page }); } catch {} }
      else { await navigator.clipboard?.writeText(e.page); toast("Link copied"); }
    }
  });
})();
