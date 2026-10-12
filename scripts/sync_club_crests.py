import argparse
import json
import struct
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SITE = Path(__file__).resolve().parents[1] / "site"
MANIFEST = SITE / "data/crests.json"
SVG = "http://www.w3.org/2000/svg"


def prepare(content):
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(content) < 24:
            raise ValueError("Incomplete PNG header")
        width, height = struct.unpack(">II", content[16:24])
        if max(width, height) < 240:
            raise ValueError(f"PNG is only {width}×{height}; need at least 240 px for 80 px at 3×")
        return content, "png", {"width": width, "height": height}
    root = ElementTree.fromstring(content)
    if root.tag != f"{{{SVG}}}svg" or any(node.tag == f"{{{SVG}}}image" for node in root.iter()):
        raise ValueError("Expected a vector SVG without embedded raster images")
    if not root.get("viewBox"):
        width = float(root.get("width", "0").removesuffix("px"))
        height = float(root.get("height", "0").removesuffix("px"))
        if min(width, height) <= 0:
            raise ValueError("SVG needs a viewBox or explicit dimensions")
        root.set("viewBox", f"0 0 {width:g} {height:g}")
        ElementTree.register_namespace("", SVG)
        content = ElementTree.tostring(root)
    view_box = list(map(float, root.get("viewBox").replace(",", " ").split()))
    if len(view_box) != 4 or min(view_box[2:]) <= 0:
        raise ValueError("Invalid SVG viewBox")
    return content, "svg", {}


def main():
    parser = argparse.ArgumentParser(description="Download and check club crests from their recorded sources.")
    parser.add_argument("--refresh", action="store_true", help="Redownload existing assets; failed downloads keep the old file")
    parser.add_argument("--check", action="store_true", help="Validate coverage and local files without downloading")
    args = parser.parse_args()
    if args.check and args.refresh:
        parser.error("--check and --refresh cannot be used together")
    manifest = json.loads(MANIFEST.read_text())
    required = set()
    for path in (SITE / "data").glob("*.json"):
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            required.update(str(team["id"]) for team in data.get("teams", []))
    for path in (SITE / "data/matches").glob("*.json"):
        for match in json.loads(path.read_text())["matches"]:
            required.update(str(match[key]) for key in ("home_id", "away_id"))
    errors = [f"Missing manifest entry for club {club_id}" for club_id in sorted(required - manifest.keys())]
    for club_id, crest in manifest.items():
        path = SITE / crest["path"]
        try:
            if not args.check and (args.refresh or not path.exists()):
                request = Request(crest["source"], headers={"User-Agent": "FinalTable/1.0"})
                with urlopen(request, timeout=20) as response:
                    content, extension, dimensions = prepare(response.read())
                if path.suffix != f".{extension}":
                    raise ValueError("Source format changed; update the manifest path first")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                crest.pop("width", None)
                crest.pop("height", None)
                crest.update(dimensions)
            _, extension, dimensions = prepare(path.read_bytes())
            if path.name != f"{club_id}.{extension}" or any(crest.get(key) != value for key, value in dimensions.items()):
                raise ValueError("Manifest path or dimensions do not match the asset")
        except (OSError, ValueError, ElementTree.ParseError) as error:
            errors.append(f"{club_id} ({crest['name']}): {error}")
    if not args.check:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Verified {len(required)} clubs; {len(manifest)} local crests")


if __name__ == "__main__":
    main()
