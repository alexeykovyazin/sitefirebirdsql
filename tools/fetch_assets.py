#!/usr/bin/env python3
"""Download the theme files (CSS, JS, fonts, logo) that the Hugo layouts use.

The asset folders (/file, /img, /template, /js, ...) are not in git. This script gets
only what the page template needs, so a local `hugo server` shows the site with styles.
Usage: python tools/fetch_assets.py [--base https://firebirdsql.org] [--out assets]
"""
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request

LAYOUTS = "site/layouts"
REF_RE = re.compile(r'(?:href|src)="(/(?:template|js|img)/[^"?#]+)')
CSS_URL_RE = re.compile(r"""url\(\s*["']?([^"')?#]+)""")


def fetch(base, path, out):
    local = os.path.join("site", "static", *path.strip("/").split("/"))
    if os.path.exists(local):  # the repo has its own copy (it wins over assets)
        return local
    dst = os.path.join(out, *path.strip("/").split("/"))
    if os.path.exists(dst):
        return dst
    req = urllib.request.Request(base + urllib.parse.quote(path), headers={"User-Agent": "Mozilla/5.0 fb-site-dev"})
    try:
        data = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:  # missing file on the server: report and go on
        print("skip %s (%s)" % (path, e))
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(data)
    print("got  %s" % path)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://firebirdsql.org")
    ap.add_argument("--out", default="assets")
    a = ap.parse_args()
    base = a.base.rstrip("/")

    refs = set()
    for d, _, fs in os.walk(LAYOUTS):
        for n in fs:
            refs.update(REF_RE.findall(open(os.path.join(d, n), encoding="utf-8").read()))
    for path in sorted(refs):
        dst = fetch(base, path, a.out)
        if dst and path.endswith(".css"):
            # Fonts and images used by the stylesheet.
            for u in CSS_URL_RE.findall(open(dst, encoding="utf-8", errors="replace").read()):
                if not u.startswith(("data:", "http:", "https:", "//")):
                    fetch(base, urllib.parse.urljoin(path, u.strip()), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
