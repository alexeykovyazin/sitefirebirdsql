#!/usr/bin/env python3
"""Build Hugo layouts from one canonical page of the new CMS template.

head.html / header.html / footer.html are cut from the original HTML, so the
static site uses exactly the same markup, CSS and JS as the CMS.
Usage: python converter/make_layouts.py [raw/pages/en/firebird-5-0/index.html] [site]
"""
import os
import re
import sys

src = sys.argv[1] if len(sys.argv) > 1 else "raw/pages/en/firebird-5-0/index.html"
site = sys.argv[2] if len(sys.argv) > 2 else "site"
h = open(src, encoding="utf-8").read()

head_start = h.find("<head>") + len("<head>")
head_end = h.find("</head>")
head = h[head_start:head_end]

# Per-page values -> front matter.
def sub_meta(attr, key, expr):
    global head
    head = re.sub(r'<meta\s+%s="%s"\s+content="[^"]*"\s*/?>' % (attr, re.escape(key)),
                  '{{ with %s }}<meta %s="%s" content="{{ . }}" />{{ end }}' % (expr, attr, key), head)

sub_meta("name", "description", ".Params.description")
sub_meta("name", "keywords", ".Params.keywords")
sub_meta("name", "generator", "false")
for k in ("title", "description", "image", "site_name"):
    sub_meta("property", "og:" + k, ".Params.og_%s" % k)
head = re.sub(r"<title>.*?</title>", "<title>{{ .Params.html_title | default .Title }}</title>", head, flags=re.S)
head += ('{{ with .Params.source_url }}<link rel="canonical" href="https://firebirdsql.org{{ . }}" />{{ end }}\n'
         '<link rel="stylesheet" href="/site-extra.css">\n')

a = h.find('<header class="header-area')
b = h.find("</header>", a) + len("</header>")
header = h[a:b]
header = re.sub(r'<a href="([^"]+)" class="(?:active)?">',
                lambda m: '<a href="%s" class="{{ if eq $.Params.menu_active "%s" }}active{{ end }}">' % (m.group(1), m.group(1)),
                header)
# Portuguese is not migrated: keep only English in the language selector.
header = re.sub(r'\s*<option[^>]*value="/pt/[^"]*"[^>]*>.*?</option>', "", header, flags=re.S)

c = h.find('<footer class="footer-area"')
footer = h[c:h.find("</html>")]
footer = footer.replace("</body>", "")

body_tag = re.search(r"<body[^>]*>", h).group(0)

L = os.path.join(site, "layouts")
os.makedirs(os.path.join(L, "partials"), exist_ok=True)
os.makedirs(os.path.join(L, "_default"), exist_ok=True)
open(os.path.join(L, "partials", "head.html"), "w", encoding="utf-8", newline="\n").write(head)
open(os.path.join(L, "partials", "header.html"), "w", encoding="utf-8", newline="\n").write(header)
open(os.path.join(L, "partials", "footer.html"), "w", encoding="utf-8", newline="\n").write(footer)
open(os.path.join(L, "_default", "baseof.html"), "w", encoding="utf-8", newline="\n").write(
    '<!DOCTYPE html>\n<html lang="en">\n<head>{{ partial "head.html" . }}</head>\n%s\n'
    '{{ partial "header.html" . }}\n{{ block "main" . }}{{ end }}\n{{ partial "footer.html" . }}\n</body>\n</html>\n' % body_tag)
main = '{{ define "main" }}{{ .Content }}{{ end }}\n'
for name in ("single.html", "list.html"):
    open(os.path.join(L, "_default", name), "w", encoding="utf-8", newline="\n").write(main)
print("layouts written to", L)
