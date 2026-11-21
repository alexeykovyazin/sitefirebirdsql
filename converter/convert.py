#!/usr/bin/env python3
"""Convert crawled CMS pages (raw/pages + raw/inventory.csv) into Hugo content.

Output:
  site/content/pages/<id>.html   one file per unique English page (front matter + raw HTML body)
  site/static/_redirects.map     nginx map: old URL -> new URL (301)
  raw/conversion.csv             url, format, target, content file

Body HTML is kept as is (between </header> and <footer>), so the page looks the same.
A file in converter/manual/ with the same name replaces the generated page (hand edits).
Usage: python converter/convert.py [--raw raw] [--site site]
"""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sys

SITE_HOSTS = r"(?:https?:)?//(?:www\.|cms(?:-[a-z0-9]+)?\.|new\.|dfp\.)?firebirdsql\.org"


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def page_file(raw, url):
    name = url.split("?")[0].strip("/")
    return os.path.join(raw, "pages", *name.split("/"), "index.html") if name else os.path.join(raw, "pages", "index.html")


def meta(h, attr, key):
    m = re.search(r'<meta\s+%s="%s"\s+content="([^"]*)"' % (attr, re.escape(key)), h, re.I)
    return html.unescape(m.group(1)) if m else ""


def relink(s):
    """Absolute links to our own hosts -> site-relative."""
    s = re.sub(r'((?:href|src|action)\s*=\s*["\'])' + SITE_HOSTS + r'(/[^"\']*)?', lambda m: m.group(1) + (m.group(2) or "/"), s, flags=re.I)
    return s


def parse_new(h):
    a = h.find('<header class="header-area')
    b = h.find("</header>", a)
    c = h.find('<footer class="footer-area"')
    if a < 0 or b < 0 or c < 0:
        return None
    header = h[a:b]
    m = re.search(r'<a href="([^"]+)" class="active">', header)
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    body = h[b + len("</header>"):c]
    # Portuguese is not migrated: drop language switcher options pointing to /pt/.
    return {
        "html_title": html.unescape(title.group(1).strip()) if title else "",
        "description": meta(h, "name", "description"),
        "keywords": meta(h, "name", "keywords"),
        "og": {k: meta(h, "property", "og:" + k) for k in ("title", "description", "image", "site_name")},
        "menu_active": m.group(1) if m else "",
        "body": body,
    }


def parse_legacy(h):
    """Old template: take only the page content, drop old navigation."""
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    a = h.find('<section class="section_page_content">')
    c = h.find('<section class="section_footer">')
    if a < 0 or c < 0:
        return None
    body = h[a:c]
    # Remove old in-page menu (content_menu_wrap ... content_menu_mob block) by cutting to the 2nd row.
    i = body.find('<div class="content_menu_wrap">')
    j = body.find('<div class="row flex-column-reverse')
    if i >= 0 and j > i:
        body = body[:i] + body[j:]
    crumbs = re.findall(r'<a href="([^"]+)" class="[^"]*page_menu[^"]*">([^<]+)</a>', h)
    crumbs = list(dict.fromkeys(crumbs))  # desktop and mobile menus repeat the same path
    bc = "".join('<li class="breadcrumb-item"><a href="%s">%s</a></li>' % (u, t.strip()) for u, t in crumbs)
    body = ('\n<section class="post-layout-1-area post-layout-3-area pb-80">\n<div class="container custom-container">\n'
            '<nav aria-label="breadcrumb"><ol class="breadcrumb">%s</ol></nav>\n<div class="legacy-content">\n%s\n</div>\n</div>\n</section>\n') % (bc, body)
    return {
        "html_title": html.unescape(title.group(1).strip()) if title else "",
        "description": meta(h, "name", "description"),
        "keywords": meta(h, "name", "keywords"),
        "og": {k: meta(h, "property", "og:" + k) for k in ("title", "description", "image", "site_name")},
        "menu_active": "",
        "body": body,
    }


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--site", default="site")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(args.raw, "inventory.csv"), encoding="utf-8")))
    by_url = {r["url"]: r for r in rows}

    out_dir = os.path.join(args.site, "content", "pages")
    os.makedirs(out_dir, exist_ok=True)
    for n in os.listdir(out_dir):  # empty the dir, keep it (Windows may lock the dir itself)
        os.remove(os.path.join(out_dir, n))
    with open(os.path.join(out_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("---\nbuild:\n  render: never\n  list: never\n---\n")

    # Group English 200 pages by content hash: "/x" and "/x/" with the same body -> one file.
    groups = {}
    for r in rows:
        if r["kind"] != "page" or r["status"] != "200" or r["lang"] != "en" or r["format"] not in ("new", "legacy"):
            continue
        groups.setdefault(r["sha256"], []).append(r)

    conv = []
    redirects = {}
    served = set()
    for sha, rs in groups.items():
        # Canonical URL: most links in; prefer the form without trailing slash on ties.
        rs.sort(key=lambda r: (-int(r["links_in"] or 0), r["url"].endswith("/"), len(r["url"])))
        canon = rs[0]
        url = canon["url"]
        h = read(page_file(args.raw, url))
        p = parse_new(h) if canon["format"] == "new" else parse_legacy(h)
        if p is None:
            conv.append((url, canon["format"], "manual", ""))
            continue
        fid = "home" if url == "/" else re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
        if len(fid) > 120:
            fid = fid[:100] + "-" + hashlib.md5(url.encode()).hexdigest()[:8]
        fname = fid + ".html"
        body = relink(p["body"])
        # nginx serves "/x" and "/x/" from x/index.html; a dot in the last segment would make Hugo write a file.
        hugo_url = url if url.endswith("/") or "." not in url.rsplit("/", 1)[-1] else url + "/"
        fm = ["---",
              "title: " + yaml_str(p["html_title"] or p["og"]["title"]),
              "html_title: " + yaml_str(p["html_title"]),
              "description: " + yaml_str(p["description"]),
              "keywords: " + yaml_str(p["keywords"]),
              "og_title: " + yaml_str(p["og"]["title"]),
              "og_description: " + yaml_str(p["og"]["description"]),
              "og_image: " + yaml_str(p["og"]["image"]),
              "og_site_name: " + yaml_str(p["og"]["site_name"]),
              "menu_active: " + yaml_str(p["menu_active"]),
              "source_url: " + yaml_str(url),
              "source_format: " + canon["format"],
              "url: " + yaml_str(hugo_url),
              "---", ""]
        target_file = os.path.join(out_dir, fname)
        manual = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual", fname)
        if os.path.exists(manual):
            # Page edited by hand (converter/manual/<file>): it wins over the CMS copy.
            shutil.copyfile(manual, target_file)
            served.add(url.rstrip("/") or "/")
            for r in rs:
                conv.append((r["url"], r["format"], "manual-override" if r is canon else "same-as " + url, fname))
                if r is not canon and r["url"].rstrip("/") != url.rstrip("/"):
                    redirects[r["url"]] = url
            continue
        if url == "/":  # Hugo home page
            target_file = os.path.join(args.site, "content", "_index.html")
            fm = [l for l in fm if not l.startswith("url: ")]
        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(fm) + body)
        served.add(url.rstrip("/") or "/")
        for r in rs:
            target = "converted" if r is canon else "same-as " + url
            conv.append((r["url"], r["format"], target, fname))
            # The other slash form is served by nginx try_files; different paths need a redirect.
            if r is not canon and r["url"].rstrip("/") != url.rstrip("/"):
                redirects[r["url"]] = url

    # Download interstitial (/download-file?file=URL): one static page, the file URL comes from the query.
    tpl = os.path.join(args.raw, "templates", "download-file.html")
    if os.path.exists(tpl):
        p = parse_new(read(tpl))
        body = relink(p["body"])
        m = re.search(r"var fileUrl = '([^']*)';", body)
        if m:
            sample = m.group(1)
            body = body.replace('href="%s"' % sample, 'href="#" id="fb-download-link"')
            body = body.replace(m.group(0),
                "var fileUrl = (function () {\n"
                "        var u = new URLSearchParams(location.search).get('file') || '';\n"
                "        try { var h = new URL(u).hostname; } catch (e) { return ''; }\n"
                "        // Only known download hosts: no open redirect.\n"
                "        var ok = /(^|\\.)(github\\.com|githubusercontent\\.com|sourceforge\\.net|firebirdsql\\.org)$/.test(h);\n"
                "        if (ok) { var a = document.getElementById('fb-download-link'); if (a) a.href = u; }\n"
                "        return ok ? u : '';\n"
                "    })();")
        fm = ["---", "title: " + yaml_str(p["html_title"]), "html_title: " + yaml_str(p["html_title"]),
              "description: " + yaml_str(p["description"]), "menu_active: " + yaml_str(p["menu_active"]),
              "source_url: \"/download-file\"", "source_format: download", "url: \"/download-file/\"", "---", ""]
        with open(os.path.join(out_dir, "download-file.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(fm) + body)
        conv.append(("/download-file", "download", "converted (JS, ?file=)", "download-file.html"))

    # CMS redirects (301/302) -> permanent redirects.
    for r in rows:
        if r["kind"] == "page" and r["status"] in ("301", "302") and r["location"]:
            redirects[r["url"]] = r["location"]
            conv.append((r["url"], "", "redirect -> " + r["location"], ""))

    # Portuguese pages -> same slug in English if it exists, else English news.
    for r in rows:
        if r["kind"] == "page" and r["lang"] == "pt" and r["status"] == "200":
            en = "/en/" + r["url"][len("/pt/"):]
            tgt = en if (en.rstrip("/") in served) else "/en/news"
            redirects[r["url"]] = tgt
            conv.append((r["url"], "pt", "redirect -> " + tgt, ""))
    redirects.setdefault("/rss/pt/news.xml", "/rss/en/news.xml")
    # Removed duplicate / old document files -> the linked copy.
    rm_list = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", "removed-assets.tsv")
    if os.path.exists(rm_list):
        for r in csv.DictReader(open(rm_list, encoding="utf-8"), delimiter="	"):
            redirects["/" + r["old_path"]] = r["new_path"] if r["new_path"].startswith(("http://", "https://", "/")) else "/" + r["new_path"]

    static = os.path.join(args.site, "static")
    os.makedirs(static, exist_ok=True)
    with open(os.path.join(static, "_redirects.map"), "w", encoding="utf-8", newline="\n") as f:
        for k in sorted(redirects):
            if redirects[k].rstrip("/") == k.rstrip("/"):
                continue
            f.write('"%s" "%s";\n' % (k.replace('"', '\\"'), redirects[k].replace('"', '\\"')))

    with open(os.path.join(args.raw, "conversion.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "format", "target", "file"])
        w.writerows(sorted(conv))
    n = sum(1 for c in conv if c[2] == "converted")
    print("pages converted: %d, redirects: %d, manual: %d" % (n, len(redirects), sum(1 for c in conv if c[2] == "manual")))


if __name__ == "__main__":
    sys.exit(main())
