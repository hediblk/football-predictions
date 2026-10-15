# Open every view of the static site in headless Chromium and fail on a script error or an empty view.
#
# Usage: python scripts/check_site.py [--site site]
#
# Serves the directory on a local port with the data it ships, stops the browser clock at the newest forecast so
# "today" is the forecast day, and loads each competition table, two match days, the clubs ranking, two club pages,
# an upcoming match page, finished ones in After and Before mode (one with a shot report), and the model page, at desktop and phone widths, expanding a match (which must
# link its match page) and a table row. Any console error, uncaught
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
TABLE = ["#hero-in h1", "#table tbody tr.row", "#table th.vsm", "#table tbody tr.row td.vsm",
         # Race movers: a mover or the "no change" line; hidden without a frozen Monday before this week to compare with.
         "#race-moves li, #race-moves[hidden]"]
MATCH = ["#view-match .mp-hero h1", "#view-match .mp-hero .numeral", "#view-match .mp-fc .scores li", "#view-match .mp-sides tbody tr"]
# A finished fixture opens in After mode; pressing Before must bring back the pre-game forecast.
AFTER = ["#view-match .mp-hero h1", "#view-match .mp-modes [data-mode=after][aria-pressed=true]", "#view-match .mp-said", "#view-match .mp-vs tbody tr"]
# A finished league game with Understat shots adds "Chances": the shot map, the xG timeline and an openable shot list.
CHANCES = AFTER + ["#view-match .mp-shots .mp-pitch circle.shot", "#view-match .mp-xgline svg path.xh"]
VIEWPORTS = {"desktop": {"width": 1280, "height": 900}, "phone": {"width": 375, "height": 844}}
BROKEN = ["No signal", "could not be loaded", "unavailable right now"]


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    # A page loads about a hundred crests at once; the default backlog of 5 resets some connections.
    request_queue_size = 256

    def handle_error(self, request, client_address):
        pass  # a closed page cut off a download; the browser reports any failure that matters


def has_points_data(data, slug, club_id=None):
    path = data / f"matches/{slug}.json"
    if not path.exists():
        return False
    matches = json.loads(path.read_text()).get("matches", [])
    return any(match.get("status") == "FINISHED"
               and isinstance(match.get("score"), list) and len(match["score"]) == 2
               and isinstance(match.get("p"), list) and len(match["p"]) == 3
               and (club_id is None or club_id in (match.get("home_id"), match.get("away_id")))
               and (slug != "champions-league" or match.get("stage") == "LEAGUE_STAGE")
               for match in matches)


def has_xg_data(data, slug, club_id):
    path = data / f"matches/{slug}.json"
    if not path.exists():
        return False
    matches = json.loads(path.read_text()).get("matches", [])
    return any(match.get("status") == "FINISHED"
               and isinstance(match.get("score"), list) and len(match["score"]) == 2
               and isinstance(match.get("xg"), list) and len(match["xg"]) == 2
               and club_id in (match.get("home_id"), match.get("away_id"))
               for match in matches)


def routes(data):
    # (hash, selectors that must each match something, rows to try opening in turn, what an opened row shows)
    index = json.loads((data / "index.json").read_text())
    clubs = json.loads((data / "clubs.json").read_text())["clubs"]
    origin = max(entry["generated_at"] for entry in index)
    found = []
    for slug in COMPETITIONS:
        selectors = TABLE + (["#rounds .mrow", "#bracket .tie", "#ko-table tbody tr"] if slug == "champions-league" else [])
        if has_points_data(data, slug):
            selectors.append('#table tbody tr.row td.vsm[title*="finished games with a forecast"]')
        found.append((f"#{slug}", selectors, ["#table tr.row"], "#table tr.detail"))
    # "Games that matter" is hidden when no fixture in the next seven days passes the stakes bar; open a row if shown.
    found += [("#matches", ["#m-day .day-head", "#m-record-table tbody tr"], ["#m-matter:not([hidden]) .mrow"],
               "#m-matter .panel a[href^='#match/']"),
              ("#clubs", ["#c-hero h1", "#c-board .cell", "#c-rank tbody tr", "#c-scatter svg"], [], None),
              ("#model/ratings", ["#c-factors b"], [], None)]
    # The first day from the forecast on with fixtures, opening a game with something at stake if there is one.
    fixtures = [(slug, match) for slug in COMPETITIONS if (data / f"matches/{slug}.json").exists()
                for match in json.loads((data / f"matches/{slug}.json").read_text())["matches"]]
    days = sorted({match["kickoff"][:10] for _, match in fixtures})
    if days:
        day = next((d for d in days if d >= origin[:10]), days[-1])
        found.append((f"#matches/{day}", ["#m-day .mrow"], ["#m-day .mrow:has(.m-stake)", "#m-day .mrow"], "#m-day .panel a[href^='#match/']"))
    # A finished game with a reconstructed forecast and one with a published receipt, checking the origin label.
    for published in (False, True):
        played = next(((slug, match) for slug, match in fixtures
                       if match.get("score") and match.get("p") and bool(match.get("published")) == published), None)
        if played:
            slug, match = played
            label = "Published before kickoff" if published else "Reconstructed:"
            found.append((f"#matches/{match['kickoff'][:10]}", ["#m-day .mrow"],
                          [f'#m-day .mrow[data-c="{slug}"][data-id="{match["id"]}"]'],
                          f'#m-day .panel .call .dim:has-text("{label}")'))
    # Match pages: the next forecast fixture (one with stakes if there is one), then in After mode the latest finished
    # league game, Champions League game and published fixture.
    ahead = sorted((f for f in fixtures if "p" in f[1] and "score" not in f[1] and f[1]["kickoff"] >= origin), key=lambda f: f[1]["kickoff"])
    upcoming = next((f for f in ahead if f[1].get("stakes")), ahead[0] if ahead else None)
    if upcoming:
        found.append((f"#match/{upcoming[0]}/{upcoming[1]['id']}", MATCH, [], None))
    done = sorted((f for f in fixtures if "p" in f[1] and "score" in f[1]), key=lambda f: f[1]["kickoff"])
    finished = [next((f for f in reversed(done) if test(f)), None) for test in
                (lambda f: f[0] != "champions-league", lambda f: f[0] == "champions-league", lambda f: f[1].get("published"))]
    for slug, fixture_id in dict.fromkeys((f[0], f[1]["id"]) for f in finished if f):
        found.append((f"#match/{slug}/{fixture_id}", AFTER, ["#view-match .mp-modes [data-mode=before]"], "#view-match .mp-fc .scores li"))
    # The latest finished league game with a shot file, opening its shot list.
    def detail(slug, match):
        path = data / f"match/{json.loads((data / f'{slug}.json').read_text())['season'][:4]}/{slug}/{match['id']}.json"
        return json.loads(path.read_text()) if path.exists() else {}
    charted = next((f for f in reversed(done) if f[0] != "champions-league" and detail(*f).get("shots")), None)
    if charted:
        found.append((f"#match/{charted[0]}/{charted[1]['id']}", CHANCES, ["#view-match .mp-list summary"], "#view-match .mp-list[open] tbody tr"))
    # ESPN adds the paired board in both competitions, marks on the xG line or a no-shots ruler,
    # and the event feed with substitutions.
    for ucl in (False, True):
        game = next((f for f in reversed(done) if (f[0] == "champions-league") == ucl and detail(*f).get("box")), None)
        if not game:
            continue
        slug, match = game
        extra = detail(*game)
        selectors = AFTER + ["#view-match .mp-stats .mp-stat-row"]
        if extra.get("events"):
            selectors.append("#view-match .mp-feed .mp-feed-row")
            if not extra.get("shots"):
                selectors.append("#view-match .mp-ruler")
            elif any(e["type"] == "red" for e in extra["events"]):
                selectors.append("#view-match .mp-xgline rect.card")
        found.append((f"#match/{slug}/{match['id']}", selectors, [], None))
    # UEFA: a finished Champions League page with physical rows, continuous heatmap and numbered starters.
    mapped = [f for f in reversed(done) if f[0] == "champions-league" and detail(*f).get("heat")]
    game = next((f for f in mapped if f[1]["id"] == 575327), mapped[0] if mapped else None)
    if game:
        slug, match = game
        found.append((f"#match/{slug}/{match['id']}", AFTER + [
            "#view-match .mp-running .mp-stat-row:has-text('Distance')",
            "#view-match .mp-running .mp-stat-row:has-text('Sprints')",
            "#view-match .mp-running .mp-stat-row:has-text('Top speed')",
            "#view-match .mp-where .heat-surface", "#view-match .mp-where .heat-starter",
            "#view-match #mp-heat-player option", "#view-match #mp-heat-positions[aria-pressed=true]", "#view-match .mp-where .mp-dir"],
            ["#view-match [data-heat-side=a]"], "#view-match [data-heat-side=a][aria-pressed=true]"))
    # The top club, and a Champions League club from outside the five leagues if one is ranked.
    for club in [clubs[0], next((c for c in clubs if c.get("league") is None), None)]:
        if club:
            slug = club.get("league") or "champions-league"
            selectors = ["#p-hero h1", "#p-strength .gauge", "#p-tiles .tile", "#p-finish .det", "#club-profile .c-go",
                         "#p-goals .pm-xg-table"]
            if has_points_data(data, slug, club["id"]):
                selectors.append("#p-results .pm-chart svg")
            if has_xg_data(data, slug, club["id"]):
                selectors.append("#p-goals .pm-spark svg")
            interactions = []
            if club.get("league") and club.get("ucl"):
                league_selector = f'#p-results [data-pcomp="{club["league"]}"]'
                ucl_selector = '#p-results [data-pcomp="champions-league"]'
                selectors += [league_selector, ucl_selector, f'{league_selector}[aria-pressed="true"]']
                for comp_slug, button in (("champions-league", ucl_selector), (club["league"], league_selector)):
                    content = "#p-results .pm-chart svg" if has_points_data(data, comp_slug, club["id"]) else None
                    interactions.append((button, f'{button}[aria-pressed="true"]', content))
            found.append((f"#clubs/{club['slug']}", selectors, [], None, interactions))
    # Task 8: scorecard route, with calibration and cumulative record on both widths.
    if (data / "scorecard.json").exists():
        scorecard = json.loads((data / "scorecard.json").read_text())
        if scorecard["all"]["n"]:
            found.append(("#model/scorecard", ["#sc-summary tbody tr", "#sc-charts svg", "#sc-cohorts button"],
                          ["#sc-cohorts [data-cohort=published]"], "#sc-summary tbody tr"))
    return origin, found


def visit(context, url, origin, selectors, rows, opened, interactions=()):
    problems = []
    page = context.new_page()
    # A missing per-match file is a documented state (that source has no data), so its 404 is not a failure.
    optional = lambda url: "/data/match/" in url
    page.on("console", lambda msg: msg.type == "error" and not optional(msg.location.get("url", ""))
            and problems.append(f"console: {msg.text}"))
    page.on("pageerror", lambda exc: problems.append(f"exception: {exc}"))
    page.on("requestfailed", lambda req: problems.append(f"request failed: {req.url}"))
    page.on("response", lambda res: res.status >= 400 and not (res.status == 404 and optional(res.url))
            and problems.append(f"HTTP {res.status}: {res.url}"))
    page.clock.set_fixed_time(datetime.fromisoformat(origin))
    page.goto(url, wait_until="networkidle")
    for selector in selectors:
        if not page.locator(selector).count():
            problems.append(f"empty: nothing matches {selector}")
    for button, selected, content in interactions:
        if not page.locator(button).count():
            problems.append(f"empty: nothing matches {button}")
            continue
        page.locator(button).click()
        if not page.locator(selected).count():
            problems.append(f"clicking {button} did not select {selected}")
        if content and not page.locator(content).count():
            problems.append(f"clicking {button} did not render {content}")
    text = page.locator("main").inner_text()
    problems += [f"shows {phrase!r}" for phrase in BROKEN if phrase in text]
    limit = 13 if page.locator(".mp-running").count() else 10
    if page.locator(".mp-stat-row").count() > limit:
        problems.append(f"Match stats has more than {limit} rows")
    if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
        problems.append("page scrolls horizontally")
    row = next((page.locator(selector).first for selector in rows if page.locator(selector).count()), None)
    if row:
        row.click()
        page.wait_for_load_state("networkidle")
        if not page.locator(opened).count():
            problems.append(f"clicking a row did not open {opened}")
        if page.locator(".mp-modes [data-mode=before][aria-pressed=true]").count() and page.locator(".mp-stats, .mp-where").count():
            problems.append("Post-match stats are visible in Before mode")
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
