#!/usr/bin/env python3
"""
Download FREELY LICENSED photos of Lionel Messi from Wikimedia Commons (official API, no scraping),
plus a credits file for your caption.

Only these licences are accepted: CC0, public domain, CC BY, CC BY-SA.
Anything marked NC / ND / fair-use is skipped.  Credit the photographers (credits.txt does it for you).

    python3 fetch_photos.py                       # 14 photos -> media/photos, credits in media/photos/credits.txt
    python3 fetch_photos.py --count 20 --min-height 1500
    python3 fetch_photos.py --videos              # also grab freely licensed videos -> media/clips
    python3 fetch_photos.py --selftest            # offline check of the filtering/credit code

Then:  python3 make_video.py      (picks up media/photos and media/clips automatically)

NOTE: needs internet access to commons.wikimedia.org and upload.wikimedia.org.
Always LOOK at the photos (media/photos/_contact.jpg) - search results can include other people or the wrong Messi.
A free copyright licence does not give you the right to imply endorsement; keep the video editorial and credited.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "MessiTributeVideo/1.0 (https://github.com/Gabby-Css/BeTechifiedAssignments; educational fan tribute)"
META = "Artist|LicenseShortName|LicenseUrl|ImageDescription|Credit|AttributionRequired"
HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------- licence / metadata helpers
def license_ok(short_name: str) -> bool:
    """CC0 / public domain / CC BY / CC BY-SA only.  NC, ND and fair-use are rejected."""
    l = re.sub(r"[-_]", " ", (short_name or "").lower()).strip()
    if not l or re.search(r"\b(nc|nd)\b", l) or "fair use" in l or "non commercial" in l:
        return False
    return bool(re.match(r"(cc0|public domain|pd\b|cc by)", l))


def clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_page(page: dict) -> dict | None:
    """Turn one API page into a small record, or None if it has no usable image info."""
    info = (page.get("imageinfo") or [None])[0]
    if not info:
        return None
    meta = info.get("extmetadata") or {}
    val = lambda k: clean_html((meta.get(k) or {}).get("value", ""))
    return {
        "title": page.get("title", ""),
        "mime": info.get("mime", ""),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
        "url": info.get("thumburl") or info.get("url"),
        "orig_url": info.get("url"),
        "page_url": info.get("descriptionurl", ""),
        "artist": val("Artist") or val("Credit") or "Unknown author",
        "license": val("LicenseShortName"),
        "license_url": val("LicenseUrl"),
        "desc": val("ImageDescription"),
    }


def acceptable(rec: dict, min_height: int, kinds: tuple, require_messi: bool = True) -> bool:
    if not rec or not rec["url"] or not license_ok(rec["license"]):
        return False
    if not any(rec["mime"].startswith(k) for k in kinds):
        return False
    if rec["mime"].startswith("image/") and (rec["height"] < min_height or rec["width"] < 700):
        return False
    if require_messi and "messi" not in (rec["title"] + " " + rec["desc"]).lower():
        return False
    return True


def credit_line(rec: dict) -> str:
    return f'"{rec["title"].removeprefix("File:")}" by {rec["artist"]}, {rec["license"]} - {rec["page_url"]}'


def short_credit(rec: dict) -> str:
    return f'{rec["artist"]} ({rec["license"]})'


def slug(title: str) -> str:
    base = os.path.splitext(title.removeprefix("File:"))[0]
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")[:50] or "photo"


# ----------------------------------------------------------------------------- API
def api(params: dict, retries: int = 4) -> dict:
    params = dict(params, format="json", maxlag="5")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except urllib.error.URLError as e:
            raise SystemExit(
                f"Could not reach commons.wikimedia.org ({e.reason}).\n"
                "If you are running this in a sandbox, allow commons.wikimedia.org and upload.wikimedia.org in its "
                "network settings - or just run this script on your own computer."
            )
    raise SystemExit("Wikimedia API kept failing - try again later.")


def category_files(category: str, depth: int = 2, max_cats: int = 40) -> list[str]:
    """File titles in a category and its Messi-related sub-categories (breadth-first, depth-limited)."""
    seen, queue, titles = set(), [(category, 0)], []
    while queue and len(seen) < max_cats:
        cat, d = queue.pop(0)
        if cat in seen:
            continue
        seen.add(cat)
        cont = {}
        while True:
            data = api({"action": "query", "list": "categorymembers", "cmtitle": cat,
                        "cmtype": "file|subcat", "cmlimit": "500", **cont})
            for m in data.get("query", {}).get("categorymembers", []):
                if m["ns"] == 6:
                    titles.append(m["title"])
                elif m["ns"] == 14 and d + 1 < depth and "messi" in m["title"].lower():
                    queue.append((m["title"], d + 1))
            if "continue" not in data:
                break
            cont = data["continue"]
            time.sleep(0.5)
        time.sleep(0.5)
    return titles


def search_files(query: str, limit: int = 100) -> list[str]:
    data = api({"action": "query", "list": "search", "srsearch": query, "srnamespace": "6", "srlimit": str(limit)})
    return [h["title"] for h in data.get("query", {}).get("search", [])]


def fetch_records(titles: list[str], width: int = 3000) -> list[dict]:
    recs = []
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        data = api({"action": "query", "titles": "|".join(chunk), "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(width), "iiextmetadatafilter": META})
        for page in data.get("query", {}).get("pages", {}).values():
            rec = parse_page(page)
            if rec:
                recs.append(rec)
        time.sleep(0.5)
    return recs


def download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as fh:
        fh.write(r.read())


def contact_sheet(folder: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("_"))
    if not files:
        return
    cols, cw, ch = 6, 220, 330
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (20, 24, 32))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        try:
            im = Image.open(os.path.join(folder, f)).convert("RGB")
            im.thumbnail((cw - 6, ch - 26))
            sheet.paste(im, ((i % cols) * cw + 3, (i // cols) * ch + 3))
            d.text(((i % cols) * cw + 6, (i // cols) * ch + ch - 20), f[:30], fill=(220, 220, 220))
        except Exception:
            pass
    sheet.save(os.path.join(folder, "_contact.jpg"), quality=85)


# ----------------------------------------------------------------------------- main
def selftest() -> None:
    assert license_ok("CC BY-SA 4.0") and license_ok("CC BY 2.0") and license_ok("CC0") and license_ok("Public domain")
    assert license_ok("PD-old") and license_ok("cc-by-4.0") and license_ok("CC BY-SA 3.0 de")
    assert not license_ok("CC BY-NC 2.0") and not license_ok("CC BY-ND 4.0") and not license_ok("Fair use")
    assert not license_ok("") and not license_ok("All rights reserved")
    fake = {"title": "File:Lionel Messi 2022.jpg", "imageinfo": [{
        "thumburl": "https://upload.example/thumb.jpg", "url": "https://upload.example/orig.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Lionel_Messi_2022.jpg",
        "width": 4000, "height": 2667, "mime": "image/jpeg",
        "extmetadata": {"Artist": {"value": '<a href="//x">Jane <b>Doe</b></a>'},
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "ImageDescription": {"value": "Messi celebrating &amp; waving"}}}]}
    rec = parse_page(fake)
    assert rec["artist"] == "Jane Doe" and rec["desc"] == "Messi celebrating & waving", rec
    assert acceptable(rec, 1300, ("image/",))
    assert not acceptable(dict(rec, height=900), 1300, ("image/",))
    assert not acceptable(dict(rec, license="CC BY-NC 4.0"), 1300, ("image/",))
    assert not acceptable(dict(rec, title="File:Someone else.jpg", desc="not him"), 1300, ("image/",))
    assert credit_line(rec).startswith('"Lionel Messi 2022.jpg" by Jane Doe, CC BY-SA 4.0')
    assert slug("File:Lionel Messi 2022!.jpg") == "Lionel_Messi_2022"
    print("selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "media", "photos"))
    ap.add_argument("--clips-out", default=os.path.join(HERE, "media", "clips"))
    ap.add_argument("--count", type=int, default=14, help="how many photos to keep (10+ recommended)")
    ap.add_argument("--min-height", type=int, default=1300, help="skip photos shorter than this (pixels)")
    ap.add_argument("--category", default="Category:Lionel Messi")
    ap.add_argument("--query", action="append", help="extra Commons search (repeatable)")
    ap.add_argument("--videos", action="store_true", help="also download freely licensed videos to media/clips")
    ap.add_argument("--dry-run", action="store_true", help="list what would be downloaded, download nothing")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    queries = args.query or ["Lionel Messi filetype:bitmap", "Messi Argentina World Cup 2022 filetype:bitmap",
                             "Messi Inter Miami filetype:bitmap", "Messi Copa America filetype:bitmap"]
    print(f"[commons] reading {args.category} ...")
    titles = category_files(args.category)
    for q in queries:
        print(f"[commons] searching: {q}")
        titles += search_files(q)
    titles = list(dict.fromkeys(titles))
    print(f"[commons] {len(titles)} candidate files, checking licences and sizes ...")
    recs = fetch_records(titles)

    photos = [r for r in recs if acceptable(r, args.min_height, ("image/jpeg", "image/png", "image/webp"))]
    photos.sort(key=lambda r: (-min(r["height"], 4000), r["title"]))
    photos = photos[: args.count]
    videos = [r for r in recs if args.videos and acceptable(r, 0, ("video/",))][:6]
    rejected = len(recs) - len(photos) - len(videos)
    print(f"[commons] keeping {len(photos)} photos" + (f" and {len(videos)} videos" if args.videos else "") +
          f" (skipped {rejected}: wrong licence, too small, or not obviously Messi)")
    if len(photos) < 10:
        print("[commons] fewer than 10 usable photos - try --min-height 1000 or add --query terms")

    if args.dry_run:
        for r in photos + videos:
            print("  ", credit_line(r))
        return

    os.makedirs(args.out, exist_ok=True)
    lines = []
    for i, r in enumerate(photos):
        prefix = "hook_" if i < 9 else "body_"          # first 9 (highest-res) are used in the hook montage
        ext = ".png" if r["mime"] == "image/png" else ".webp" if r["mime"] == "image/webp" else ".jpg"
        dest = os.path.join(args.out, f"{prefix}{i + 1:02d}_{slug(r['title'])}{ext}")
        print(f"  [{i + 1}/{len(photos)}] {os.path.basename(dest)}")
        download(r["url"], dest)
        lines.append(credit_line(r))
        time.sleep(1.0)
    if videos:
        os.makedirs(args.clips_out, exist_ok=True)
        for i, r in enumerate(videos):
            dest = os.path.join(args.clips_out, f"clip_{i + 1:02d}_{slug(r['title'])}" + os.path.splitext(r["orig_url"])[1])
            print(f"  [video {i + 1}/{len(videos)}] {os.path.basename(dest)}")
            download(r["orig_url"], dest)
            lines.append(credit_line(r))
            time.sleep(1.0)

    with open(os.path.join(args.out, "credits.txt"), "w", encoding="utf-8") as fh:
        fh.write("PHOTO / VIDEO CREDITS (Wikimedia Commons) - paste into your caption or description\n\n")
        fh.write("Short version:\n  Photos: " + "; ".join(short_credit(r) for r in photos + videos) + " - via Wikimedia Commons\n\n")
        fh.write("Full list:\n" + "\n".join("  " + l for l in lines) + "\n")
    contact_sheet(args.out)
    print(f"[done] {len(photos)} photos in {args.out}\n       credits: {os.path.join(args.out, 'credits.txt')}"
          f"\n       look at {os.path.join(args.out, '_contact.jpg')} and delete any photo that is not Messi.")


if __name__ == "__main__":
    main()
