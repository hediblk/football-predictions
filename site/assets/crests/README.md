# Club crests

`site/data/crests.json` maps football-data.org club IDs to local files and their exact download sources. It includes Champions League participants outside the five domestic leagues. The browser only requests local assets.

Use a genuine vector SVG where possible, with a valid `viewBox` and no embedded bitmap. PNG fallbacks must have at least 240 native pixels on their longest edge: the largest display is 80 CSS pixels, so this supports 3× screens without upscaling. Prefer 500 px or more. Keep the original proportions, artwork and colours; do not trace or upscale a small bitmap. A `backing: true` entry adds a light neutral backing for dark artwork.

Sources start with the provider's `crest` URL. Some PNG URLs have a verified vector sibling on the same host; the manifest records the actual SVG used. Official club websites, published brand assets and official competition sources supply replacements for small or outdated provider images. The source URL is provenance, not evidence of a licence: crests belong to their respective owners. No owner permissions have been obtained or asserted by this change. [Football-data.org's terms](https://www.football-data.org/about) require owner consent for graphics; retain any permission and required attribution when obtained.

Como's official site only provided a small bitmap, so its SVG comes from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Calcio_Como_-_logo_(Italy,_2019-).svg). Schalke's official site supplied a horizontal wordmark, so its standalone crest also comes from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:FC_Schalke_04_Logo.svg), where it is recorded as extracted from the club's official site. Both files are tagged `PD-textlogo` with a trademark notice; the manifest retains their description pages and declared status. The current set has 106 vector SVGs and five official-club PNGs, all at least 500 px on their longest edge.

To add a club, find its `crest` in `/v4/competitions/{code}/teams?season={year}` using the existing football-data.org account, or use an official club source. Add its ID, `name`, `source` and `path` (`assets/crests/{id}.svg` or `.png`) to the manifest, then run:

```sh
python3 -B scripts/sync_club_crests.py
```

Existing files are checked without network requests. For offline validation or a deliberate refresh:

```sh
python3 -B scripts/sync_club_crests.py --check
python3 -B scripts/sync_club_crests.py --refresh
```

A failed download or a source below the quality threshold leaves the previous asset intact and reports an error. Update `source` and `path` together if the format changes; remove the superseded file after checking the replacement. Visually review identity, current artwork, transparent margins and dark-background contrast before committing. Logo refreshes are independent of the daily forecast refresh.
