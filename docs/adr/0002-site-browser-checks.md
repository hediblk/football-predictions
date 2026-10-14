---
status: accepted
date: 2026-10-14
supersedes: "ADR 0001: the safeguard omitting automated browser checks"
---

# Load the site in a headless browser before publishing it, and version its asset URLs

[ADR 0001](0001-site-model-boundary.md) left the site's JavaScript to manual review: the data contract checks the JSON, not the code that renders it. Every view now has interactions and data paths (stakes, club pages for every rated club, the bracket) that manual review misses, and a broken script fails silently for every visitor. This decision replaces 0001's "omit automated browser checks" safeguard; the rest of 0001 stands.

## Decision

- `scripts/check_site.py` serves a site directory locally and opens it in headless Chromium (Playwright, pinned in `requirements-lock.txt`): every competition table, today's matches and the first match day from the forecast on, the clubs ranking, the top club's page and a Champions League club from outside the five leagues, and the model page, at desktop and phone widths. It opens a table row and a match. Any console error, uncaught exception, failed same-origin request, missing core content or "could not be loaded" message fails the check.
- The browser clock is frozen at the newest forecast and the time zone is UTC, so "today" and the next round depend on the data, not on when the check runs. Other origins (web fonts) get empty responses, so the check needs no network.
- It runs on pull requests that touch `site/**` or the check itself (`site-check.yml`), against the data committed in that revision, and in the deploy job against the exact build being uploaded, after data validation. A failure leaves the deployed site in place, as an invalid dataset does. Daily refreshes therefore check that day's data, since their bot commits trigger no other workflow.
- At deploy, `scripts/stamp_assets.py` appends `?v=<hash of the scripts and styles>` to the stylesheet, the entry script and every module import, so a browser holding a cached page never mixes old and new code. The committed files stay unstamped; the browser checks run on the stamped build. The hash changes only with code or style changes, so daily data deploys keep browsers' cached code.

## Consequences

The check proves that every view renders from the shipped data without script errors. It does not judge layout, wording or whether numbers are right; the data contract and exporter tests still own data meaning, and a field the JavaScript tolerates being absent can still be missing. Optional-file fallbacks (missing match files, history or crests) are exercised only when the data lacks them. Deploys take about a minute longer to install Chromium. A flaky check would block a day's deploy rather than publish it; the local server is sized for the page's parallel requests to keep it deterministic.
