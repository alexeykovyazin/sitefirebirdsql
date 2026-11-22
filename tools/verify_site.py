#!/usr/bin/env python3
"""Verify files and links of the static site. Standard library only.

It checks:
  1. Every internal link (href, src, srcset, action, CSS url(), /download-file?file=)
     in site pages resolves to a page, a file, or a redirect that ends on one.
  2. Every file in the assets manifest exists and has the listed size.
  3. Which asset files and pages no page links to (orphans).

Links are followed transitively: a page links to a docs HTML file, that file links
to a PDF -> the PDF is reachable. The start set is all Hugo pages.

The resolver follows nginx order: _redirects.map, docs_redirects.conf,
then site dir ($uri, $uri/index.html, $uri.html), then assets dir.

Usage (on the droplet):
  python3 verify_site.py --site /srv/firebirdsql/current --assets /srv/firebirdsql/assets \
      --docs-redirects /etc/nginx/snippets/fb-docs-redirects.conf \
      --manifest /srv/firebirdsql/assets-manifest.tsv --out /tmp/verify
Exit code: 1 when a site page has a broken link, else 0.
Broken links inside copied files (docs HTML) are reported, but they are broken on origin too.
"""
import argparse
import csv
import collections
import html
import os
import posixpath
import re
import sys
from urllib.parse import urlsplit, unquote, parse_qs

OWN_HOSTS = re.compile(r"^(?:www\.|cms(?:-[a-z0-9]+)?\.|new\.|newtest\.|dfp\.)?firebirdsql\.org$", re.I)
ATTR_RE = re.compile(r"""\b(href|src|action|data-src|poster|srcset)\s*=\s*(["'])(.*?)\2""", re.I | re.S)
OG_IMAGE_RE = re.compile(r"""<meta\s+property=["']og:image["']\s+content=["']([^"']+)""", re.I)
CSS_URL_RE = re.compile(r"""(?<![\w.])url\(\s*(["']?)([^"')]+)\1\s*\)""", re.I)
PARSE_EXT = (".html", ".htm", ".css")
SKIP_SCHEMES = ("mailto:", "javascript:", "tel:", "data:", "ftp:", "news:", "irc:", "skype:", "#")
DOC_EXT = {".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".txt", ".gz",
           ".bz2", ".7z", ".rar", ".tar", ".chm", ".epub", ".sql", ".fdb", ".fbk", ".exe", ".msi", ".rtf"}
INFRA_FILES = {"google27b5d15e48805187.html",  # Google Search Console site verification
               "robots.txt", "favicon.ico", "404.html", "50x.html", "sitemap.xml", "_redirects.map"}


def load_redirect_map(path):
    m = {}
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"\s*;', line)
            if r:
                m[r.group(1).replace('\\"', '"')] = r.group(2).replace('\\"', '"')
    return m


def load_docs_redirects(path):
    """Parse 'location = X { return C Y; }' and 'rewrite RE REPL [flag];' lines."""
    exact, rules = {}, []
    if not path or not os.path.exists(path):
        return exact, rules
    text = open(path, encoding="utf-8").read()
    for loc, tgt in re.findall(r"location\s*=\s*(\S+)\s*\{\s*return\s+\d+\s+(\S+?);\s*\}", text):
        exact[loc] = tgt
    for rx, repl in re.findall(r"^\s*rewrite\s+(\S+)\s+(\S+?)(?:\s+\w+)?\s*;", text, re.M):
        try:
            rules.append((re.compile(rx), re.sub(r"\$(\d)", r"\\\1", repl)))
        except re.error:
            pass
    return exact, rules


class Site:
    def __init__(self, site, assets, redirects, docs):
        self.site, self.assets = site, assets
        self.redirects = redirects
        self.docs_exact, self.docs_rules = docs

    def _file(self, root, path):
        p = unquote(path)
        base = os.path.join(root, p.lstrip("/"))
        for cand in (base, os.path.join(base, "index.html"), base.rstrip("/") + ".html"):
            if os.path.isfile(cand):
                return os.path.realpath(cand)
        return None

    def resolve(self, uri):
        """uri = path[?query]. Returns (kind, file_or_target, chain)."""
        chain = []
        for _ in range(8):
            path = uri.split("?", 1)[0]
            tgt = self.redirects.get(uri) or self.docs_exact.get(path)
            if not tgt:
                for rx, repl in self.docs_rules:
                    if rx.search(path):
                        tgt = rx.sub(repl, path, count=1)
                        break
            if tgt:
                chain.append(tgt)
                s = urlsplit(tgt)
                if s.netloc and not OWN_HOSTS.match(s.hostname or ""):
                    return "external-redirect", tgt, chain
                uri = (s.path or "/") + ("?" + s.query if s.query else "")
                continue
            f = self._file(self.site, path)
            if f:
                return "page" if f.endswith((".html", ".htm")) else "site-file", f, chain
            f = self._file(self.assets, path)
            if f:
                return "asset", f, chain
            return "missing", path, chain
        return "redirect-loop", uri, chain


def page_url(root, f):
    rel = "/" + os.path.relpath(f, root).replace(os.sep, "/")
    return rel[: -len("index.html")] if rel.endswith("/index.html") else rel


def extract(text, is_css):
    if is_css:
        for m in CSS_URL_RE.finditer(text):
            yield m.group(2).strip()
        return
    for m in OG_IMAGE_RE.finditer(text):  # social preview image
        yield html.unescape(m.group(1).strip())
    for m in ATTR_RE.finditer(text):
        v = html.unescape(m.group(3).strip())
        if m.group(1).lower() == "srcset":
            for part in v.split(","):
                if part.strip():
                    yield part.strip().split()[0]
        else:
            yield v
    for m in CSS_URL_RE.finditer(text):  # inline style="background:url(...)"
        yield html.unescape(m.group(2).strip())


def normalize(link, base_url):
    """Return internal 'path[?query]' or None for external/skip."""
    link = re.sub(r"[\t\r\n]", "", link)  # browsers drop these inside URLs
    if not link or link.lower().startswith(SKIP_SCHEMES) or "{{" in link or "${" in link or "'+" in link or "+'" in link or link.startswith("~/"):
        return None
    s = urlsplit(link)
    if s.scheme and s.scheme not in ("http", "https"):
        return None
    if s.netloc:
        if not OWN_HOSTS.match(s.hostname or ""):
            return None
        path = s.path or "/"
    else:
        if not s.path:
            return None
        path = s.path if s.path.startswith("/") else posixpath.join(posixpath.dirname(base_url), s.path)
        trail = path.endswith("/")
        path = posixpath.normpath(path) + ("/" if trail and path != "/" else "")
    if path.startswith("/download-file"):
        f = parse_qs(s.query).get("file", [""])[0]
        if f:
            fs = urlsplit(f)
            if fs.netloc and OWN_HOSTS.match(fs.hostname or ""):
                return fs.path or "/"
        return "/download-file"
    return path + ("?" + s.query if s.query else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True, help="Hugo output (public/ or /srv/firebirdsql/current)")
    ap.add_argument("--assets", required=True, help="files copied from origin")
    ap.add_argument("--redirects", help="nginx map file (default: SITE/_redirects.map)")
    ap.add_argument("--docs-redirects", help="docs_redirects.conf")
    ap.add_argument("--manifest", help="assets-manifest.tsv: path<TAB>size")
    ap.add_argument("--out", default="verify-report")
    a = ap.parse_args()
    site_root, assets_root = os.path.realpath(a.site), os.path.realpath(a.assets)
    os.makedirs(a.out, exist_ok=True)
    s = Site(site_root, assets_root, load_redirect_map(a.redirects or os.path.join(site_root, "_redirects.map")),
             load_docs_redirects(a.docs_redirects))

    # Start set: all Hugo pages.
    queue, seen_files = collections.deque(), set()
    pages = []
    for d, _, fs in os.walk(site_root):
        for n in fs:
            if n.endswith(".html"):
                f = os.path.realpath(os.path.join(d, n))
                pages.append(f)
                seen_files.add(f)
                queue.append((f, page_url(site_root, f)))
    # CMS banners: GetBanners() in /js/functions-min.js loads /68854C93/68854C93.js (the banner list),
    # then /68854C93/<file>/<file>.html for each listed file.
    blist = os.path.join(assets_root, "68854C93", "68854C93.js")
    if os.path.isfile(blist):
        seen_files.add(os.path.realpath(blist))
        for name in re.findall(r"file\s*:\s*'([^']+)'", open(blist, encoding="utf-8", errors="replace").read()):
            f = os.path.realpath(os.path.join(assets_root, "68854C93", name, name + ".html"))
            if os.path.isfile(f):
                seen_files.add(f)
                queue.append((f, "/68854C93/%s/%s.html" % (name, name)))

    broken, inbound = [], collections.Counter()
    checked = {}
    n_links = n_external = 0
    while queue:
        f, url = queue.popleft()
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for link in set(extract(text, f.endswith(".css"))):
            n_links += 1
            uri = normalize(link, url)
            if uri is None:
                n_external += 1
                continue
            if uri not in checked:
                checked[uri] = s.resolve(uri)
            kind, target, chain = checked[uri]
            if kind in ("missing", "redirect-loop"):
                src = "page" if f.startswith(site_root + os.sep) else "copied-file"
                broken.append((src, url, link, kind, " -> ".join(chain) or target))
                continue
            if kind == "external-redirect":
                continue
            if target != f:
                inbound[target] += 1
            if target not in seen_files:
                seen_files.add(target)
                if kind == "asset" and target.lower().endswith(PARSE_EXT):
                    queue.append((target, "/" + os.path.relpath(target, assets_root).replace(os.sep, "/")))
                elif kind == "site-file" and target.lower().endswith(".css"):
                    queue.append((target, "/" + os.path.relpath(target, site_root).replace(os.sep, "/")))

    # Manifest check: every listed file exists with the same size.
    bad_files = []
    if a.manifest and os.path.exists(a.manifest):
        for line in open(a.manifest, encoding="utf-8", errors="replace"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            p = os.path.join(assets_root, parts[0])
            if not os.path.isfile(p):
                bad_files.append((parts[0], "missing", parts[1], ""))
            elif str(os.path.getsize(p)) != parts[1]:
                bad_files.append((parts[0], "size differs", parts[1], os.path.getsize(p)))
            elif parts[1] == "0":
                bad_files.append((parts[0], "empty file", "0", "0"))

    # Runtime files that pages load from JavaScript (not visible as links).
    for d, dirs, fs in os.walk(assets_root):
        script = os.path.realpath(os.path.join(d, "script.js"))
        if script in seen_files and ("element-list" in fs or "package-list" in fs):
            # javadoc root: script.js loads jquery/*, search.js and *-search-index.*;
            # legal/ holds license notices; element-list/package-list serve external javadoc links;
            # overview-summary.html is the old entry URL (redirect stub to index.html).
            for sd, _, sfs in os.walk(d):
                rel = os.path.relpath(sd, d).replace(os.sep, "/")
                for n in sfs:
                    if rel.split("/")[0] in ("jquery", "legal") or (rel == "." and (
                            n in ("search.js", "element-list", "package-list", "overview-summary.html")
                            or "-search-index." in n)):
                        seen_files.add(os.path.realpath(os.path.join(sd, n)))
        if "persistent-toc.html" in fs and any(os.path.realpath(os.path.join(d, n)) in seen_files
                                                 for n in fs if n.endswith(".html") and n != "persistent-toc.html"):
            seen_files.add(os.path.realpath(os.path.join(d, "persistent-toc.html")))  # firebird-persistent-toc.js

    # Orphans: asset files that no page (directly or through docs HTML/CSS) links to.
    orphans = []
    for d, dirs, fs in os.walk(assets_root):
        for n in fs:
            f = os.path.realpath(os.path.join(d, n))
            if f in seen_files or not os.path.isfile(f):  # skip broken symlinks
                continue
            rel = os.path.relpath(f, assets_root).replace(os.sep, "/")
            if rel in INFRA_FILES:
                continue
            orphans.append((rel, os.path.getsize(f), os.path.splitext(n)[1].lower() or "(none)", rel.split("/")[0]))
    orphans.sort()
    home = os.path.join(site_root, "index.html")
    orphan_pages = sorted(page_url(site_root, p) for p in pages
                          if inbound[p] == 0 and p != home and os.path.basename(p) not in INFRA_FILES)

    def write(name, header, rows):
        with open(os.path.join(a.out, name), "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    write("broken_links.csv", ["source_type", "source", "link", "reason", "resolved"], sorted(broken))
    write("bad_files.csv", ["path", "problem", "manifest_size", "disk_size"], bad_files)
    write("orphan_files.csv", ["path", "size", "ext", "top_dir"], orphans)
    write("orphan_documents.csv", ["path", "size", "ext", "top_dir"], [o for o in orphans if o[2] in DOC_EXT])
    write("orphan_pages.csv", ["url"], [(u,) for u in orphan_pages])

    by_dir = collections.Counter(o[3] for o in orphans)
    by_ext = collections.Counter(o[2] for o in orphans)
    size_dir = collections.Counter()
    for o in orphans:
        size_dir[o[3]] += o[1]
    broken_targets = collections.Counter(b[4] for b in broken)
    n_page_broken = sum(1 for b in broken if b[0] == "page")
    lines = [
        "pages scanned: %d, files reached: %d, links: %d (external/skipped: %d)" % (len(pages), len(seen_files), n_links, n_external),
        "broken links: %d (in site pages: %d, in copied files: %d; unique targets: %d)" % (
            len(broken), n_page_broken, len(broken) - n_page_broken, len(broken_targets)),
        "bad files (manifest): %d" % len(bad_files),
        "orphan files: %d, %.1f MB (documents: %d)" % (len(orphans), sum(o[1] for o in orphans) / 1e6,
                                                 sum(1 for o in orphans if o[2] in DOC_EXT)),
        "orphan pages (no inbound link): %d" % len(orphan_pages),
        "", "orphan files by top dir:",
    ] + ["  %-20s %6d  %8.1f MB" % (k, v, size_dir[k] / 1e6) for k, v in by_dir.most_common()] + [
        "", "orphan files by extension:",
    ] + ["  %-10s %6d" % (k, v) for k, v in by_ext.most_common(15)] + [
        "", "top broken targets:",
    ] + ["  %4d  %s" % (v, k) for k, v in broken_targets.most_common(20)]
    open(os.path.join(a.out, "summary.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if n_page_broken else 0


if __name__ == "__main__":
    sys.exit(main())
