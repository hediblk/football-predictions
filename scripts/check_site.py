# Open every view of the static site in headless Chromium and fail on a script error or an empty view.
#
# Usage: python scripts/check_site.py [--site site]
#
# Serves the directory on a local port with the data it ships, stops the browser clock at the newest forecast so
# "today" is the forecast day, and loads each competition table, two match days, the clubs ranking, two club pages
# and the model page, at desktop and phone widths, expanding a match and a table row. Any console error, uncaught
# exception, failed same-origin request or missing content fails the check. Other origins (web fonts) get empty
# responses, so the check runs offline. Needs `pip install playwright` and `python -m playwright install chromium`.

import argparse
import json
import threading
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

COMPETITIONS = ["la-liga", "premier-league", "bundesliga", "ligue-1", "serie-a", "champions-league"]
TABLE = ["#hero-in h1", "#table tbody tr.row"]
VIEWPORTS = {"desktop": {"width": 1280, "height": 900}, "phone": {"width": 390, "height": 844}}
BROKEN = ["No signal", "could not be loaded", "unavailable right now"]


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    # A page loads about a hundred crests at once; the default backlog of 5 resets some connections.
    request_queue_size = 256

    def handle_error(self, request, client_address):
        pass  # a closed page cut off a download; the browser reports any failure that matters


def routes(data):
    # (hash, selectors that must each match something, rows to try opening in turn, what an opened row shows)
    index = json.loads((data / "index.json").read_text())
    clubs = json.loads((data / "clubs.json").read_text())["clubs"]
    origin = max(entry["generated_at"] for entry in index)
    found = [(f"#{slug}", TABLE + (["#rounds .mrow", "#bracket .tie", "#ko-table tbody tr"] if slug == "champions-league" else []),
              ["#table tr.row"], "#table tr.detail") for slug in COMPETITIONS]
    found += [("#matches", ["#m-day .day-head", "#m-record-table tbody tr"], [], None),
              ("#clubs", ["#c-hero h1", "#c-board .cell", "#c-rank tbody tr", "#c-scatter svg"], [], None),
              ("#model/ratings", ["#c-factors b"], [], None)]
    # The first day from the forecast on with fixtures, opening a game with something at stake if there is one.
    days = sorted({match["kickoff"][:10] for slug in COMPETITIONS if (data / f"matches/{slug}.json").exists()
                   for match in json.loads((data / f"matches/{slug}.json").read_text())["matches"]})
    if days:
        day = next((d for d in days if d >= origin[:10]), days[-1])
        found.append((f"#matches/{day}", ["#m-day .mrow"], ["#m-day .mrow:has(.m-stake)", "#m-day .mrow"], "#m-day .panel"))
    # The top club, and a Champions League club from outside the five leagues if one is ranked.
    for club in [clubs[0], next((c for c in clubs if c.get("league") is None), None)]:
        if club:
            found.append((f"#clubs/{club['slug']}", ["#p-hero h1", "#p-strength .gauge", "#p-tiles .tile", "#p-finish .det"], [], None))
    return origin, found


def visit(context, url, origin, selectors, rows, opened):
    problems = []
    page = context.new_page()
    page.on("console", lambda msg: msg.type == "error" and problems.append(f"console: {msg.text}"))
    page.on("pageerror", lambda exc: problems.append(f"exception: {exc}"))
    page.on("requestfailed", lambda req: problems.append(f"request failed: {req.url}"))
    page.on("response", lambda res: res.status >= 400 and problems.append(f"HTTP {res.status}: {res.url}"))
    page.clock.set_fixed_time(datetime.fromisoformat(origin))
    page.goto(url, wait_until="networkidle")
    for selector in selectors:
        if not page.locator(selector).count():
            problems.append(f"empty: nothing matches {selector}")
    text = page.locator("main").inner_text()
    problems += [f"shows {phrase!r}" for phrase in BROKEN if phrase in text]
    row = next((page.locator(selector).first for selector in rows if page.locator(selector).count()), None)
    if row:
        row.click()
        page.wait_for_load_state("networkidle")
        if not page.locator(opened).count():
            problems.append(f"clicking a row did not open {opened}")
    page.close()
    return problems


def check(site):
    site = Path(site).resolve()
    origin, pages = routes(site / "data")
    server = Server(("127.0.0.1", 0), partial(Quiet, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, viewport in VIEWPORTS.items():
            context = browser.new_context(viewport=viewport, timezone_id="UTC", locale="en-GB")
            context.route(lambda url: not url.startswith(base), lambda route: route.fulfill(status=200, body=""))
            for route, *checks in pages:
                failures += [f"{width} {route}: {problem}" for problem in visit(context, base + route, origin, *checks)]
            context.close()
        browser.close()
    server.shutdown()
    return len(pages) * len(VIEWPORTS), failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Load every view of the static site in headless Chromium.")
    parser.add_argument("--site", type=Path, default=Path("site"))
    args = parser.parse_args(argv)
    count, failures = check(args.site)
    if failures:
        parser.exit(1, "\n".join(failures) + "\n")
    print(f"Checked {count} page loads without errors")


if __name__ == "__main__":
    main()
