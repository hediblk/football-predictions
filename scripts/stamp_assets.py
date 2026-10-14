# Version the site's script and style URLs so a browser never runs cached code against newer files.
#
# Usage: python scripts/stamp_assets.py [site]
#
# Appends `?v=<hash of every script and stylesheet>` to the asset URLs in index.html and to the module imports
# inside assets/*.js, rewriting them in place. The deploy runs it on its checkout before upload; the committed
# files stay unstamped. The hash changes only when code or styles change, so daily data deploys keep browser caches.

import hashlib
import re
import sys
from pathlib import Path

STAMP = r"(?:\?v=\w+)?"
PAGE = re.compile(rf'((?:href|src)="assets/[\w.-]+\.(?:css|js)){STAMP}"')
IMPORT = re.compile(rf'((?:from|import)\s*\(?\s*"\./[\w.-]+\.js){STAMP}"')


def stamp(site):
    site = Path(site)
    assets = sorted([*site.glob("assets/*.js"), *site.glob("assets/*.css")])
    unstamped = {path: IMPORT.sub(r'\1"', path.read_text()) for path in assets}
    version = hashlib.sha256("".join(unstamped[path] for path in assets).encode()).hexdigest()[:10]
    for path in assets:
        if path.suffix == ".js":
            path.write_text(IMPORT.sub(rf'\1?v={version}"', unstamped[path]))
    page = site / "index.html"
    html, count = PAGE.subn(rf'\1?v={version}"', page.read_text())
    if not count:
        raise SystemExit(f"No asset URLs found in {page}")
    page.write_text(html)
    return version


if __name__ == "__main__":
    print(f"Stamped site assets with v={stamp(sys.argv[1] if len(sys.argv) > 1 else 'site')}")
