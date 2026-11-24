#!/usr/bin/env python3
"""Convert an EmberWings magazine PDF into a Hugo page with a left menu.

The page keeps the PDF font sizes (1 pt = 4/3 px, so text looks like the PDF at 100% zoom).
Images are rendered from the PDF into IMG_DIR. Needs PyMuPDF (pip install pymupdf).

Usage:
  python tools/pdf_magazine.py PDF [PDF ...]
Example:
  python tools/pdf_magazine.py EmberWings-2025-02.pdf
writes site/content/extra/emberwings-2025-02.html (URL /file/emberwings/EmberWings-2025-02.html)
and its pictures to site/static/file/emberwings/EmberWings-2025-02/.

--full: pages rendered as one picture (default auto: cover, contents, last page, adverts).
--toc: contents page (default: the page with most internal links); its links give the article
start pages and the menu names.
"""
import argparse
import html
import os
import re

import pymupdf as fitz

PX = 4 / 3            # pt -> px
LEFT = 38             # left text margin of the PDF, pt
RIGHT = 574           # right text margin, pt
FOOTER_Y = 760        # page number area starts here
DARK = {0x130101, 0x000000, 0x060606, 0x1f1e1c}
TITLE_FONT = "Bitter"
TITLE_COLOR = "#7d3c98"
TERMINAL = tuple('.!?:"”)’')


def esc(s):
    return html.escape(s, quote=False)


def clean(s):
    return s.replace("​", "").replace("﻿", "")


def is_code(font):
    return "Courier" in font


def is_bold(span):
    return "Bold" in span["font"] or bool(span["flags"] & 16)


def is_italic(span):
    return "Italic" in span["font"] or bool(span["flags"] & 2)


def hexcolor(c):
    return "#%06x" % c


def light(rgb):
    return all(x > 0.985 for x in rgb)


class Page:
    def __init__(self, page):
        self.p = page
        self.links = [(fitz.Rect(l["from"]), l["uri"]) for l in page.get_links() if l.get("uri")]
        self.boxes, self.bullets = [], []
        area = page.rect
        for dr in page.get_drawings():
            r, fill = dr["rect"], dr.get("fill")
            if not fill:
                continue
            if r.width < 9 and r.height < 9:
                self.bullets.append(r)
            elif (r.width > 50 and r.height > 14 and not light(fill) and r.y0 < FOOTER_Y
                  and r.x0 >= area.x0 - 1 and r.y1 <= area.y1 + 1
                  and not (r.width > area.width - 5 and r.height > area.height - 5)):
                self.boxes.append((r, fill))

    def link_of(self, bbox):
        r = fitz.Rect(bbox)
        for lr, uri in self.links:
            i = r & lr
            if not i.is_empty and i.get_area() > 0.5 * r.get_area():
                return uri
        return None

    def box_chain(self, bbox):
        """Fill boxes that contain the element, outer first."""
        c = fitz.Rect(bbox)
        mid = fitz.Point((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2)
        found = [(r, f) for r, f in self.boxes if r.contains(mid)]
        found.sort(key=lambda b: -b[0].get_area())
        return tuple((round(r.x0), round(r.y0), round(r.x1), round(r.y1), f) for r, f in found)


def inline(spans, page, base_size):
    out, cur_uri, buf = [], None, []

    def flush():
        if not buf:
            return
        text = "".join(buf)
        out.append('<a href="%s">%s</a>' % (html.escape(cur_uri), text) if cur_uri else text)
        buf.clear()

    for s in spans:
        t = clean(s["text"])
        if not t or s["size"] < 3:
            continue
        h = esc(t)
        if is_code(s["font"]) and t.strip():
            h = "<code>%s</code>" % h
        if is_bold(s) and t.strip():
            h = "<strong>%s</strong>" % h
        if is_italic(s) and t.strip():
            h = "<em>%s</em>" % h
        uri = page.link_of(s["bbox"])
        style = []
        if s["color"] not in DARK and not uri:
            style.append("color:%s" % hexcolor(s["color"]))
        if abs(s["size"] - base_size) > 1.2 and t.strip():
            style.append("font-size:%.0fpx" % (s["size"] * PX))
        if style:
            h = '<span style="%s">%s</span>' % (";".join(style), h)
        if uri != cur_uri:
            flush()
            cur_uri = uri
        buf.append(h)
    flush()
    s = "".join(out)
    return re.sub(r"</strong><strong>|</em><em>|</code><code>", "", s)


def code_line(line, x0, cw):
    text = ""
    for s in line["spans"]:
        t = clean(s["text"])
        if not t:
            continue
        col = int(round((s["bbox"][0] - x0) / cw))
        if col > len(text):
            text += " " * (col - len(text))
        text += t
    return text.rstrip()


def main_size(spans):
    sizes = {}
    for s in spans:
        if s["text"].strip() and s["size"] >= 3:
            sizes[round(s["size"], 1)] = sizes.get(round(s["size"], 1), 0) + len(s["text"])
    return max(sizes, key=sizes.get) if sizes else 11.2


def convert_block(b, page, pno):
    """Return a list of elements (dicts) for one text block."""
    lines = [l for l in b["lines"] if "".join(clean(s["text"]) for s in l["spans"]).strip()]
    lines = [dict(l, spans=[s for s in l["spans"] if s["size"] >= 3]) for l in lines]
    lines = [l for l in lines if l["spans"]]
    if not lines:
        return []
    spans = [s for l in lines for s in l["spans"] if clean(s["text"]).strip()]
    x0, y0, x1, y1 = b["bbox"]
    size = main_size(spans)
    base = dict(bbox=b["bbox"], size=size, x0=x0, pno=pno, box=page.box_chain(b["bbox"]))

    if all(is_code(s["font"]) for s in spans):
        cw = 0.6 * size
        bx = min(l["bbox"][0] for l in lines)
        text = [code_line(l, bx, cw) for l in lines]
        return [dict(base, kind="code", lines=text, y1=y1, lh=size * 1.25)]

    full = " ".join(clean(s["text"]) for s in spans).strip()
    if spans[0]["font"].startswith(TITLE_FONT) and size > 20:
        return [dict(base, box=(), kind="h1", text=esc(full.split("In This Issue")[0] or full))]
    if all(is_bold(s) for s in spans) and len(full) < 120 and len(lines) <= 2 and spans[0]["color"] in DARK:
        lvl = "h2" if size >= 15.5 and size != 16.5 else "h3"
        return [dict(base, kind=lvl, text=inline(spans, page, size))]

    # Split the block into paragraphs and list items.
    items, cur = [], None
    width = x1 - x0
    for i, l in enumerate(lines):
        ly = (l["bbox"][1] + l["bbox"][3]) / 2
        bullet = any(abs((r.y0 + r.y1) / 2 - ly) < 5 and r.x1 <= l["bbox"][0] + 1 for r in page.bullets)
        numbered = re.match(r"\s*\d+[.)]\s", clean(l["spans"][0]["text"]) + " ") and len(lines) > 1
        if cur is None or bullet or numbered or cur.get("brk"):
            cur = dict(li=bool(bullet), spans=[])
            items.append(cur)
        elif cur["spans"]:
            last = cur["spans"][-1]
            if not last["text"].endswith((" ", "-", "/")):
                cur["spans"].append(dict(last, text=" ", font="x", flags=0, color=0x130101))
        cur["spans"].extend(l["spans"])
        # A line that ends far from the right edge closes the paragraph.
        cur["brk"] = i < len(lines) - 1 and l["bbox"][2] < x1 - 45 and width > 250
    out = []
    align = None
    if x0 > 200 and x1 > RIGHT - 15 and width < 300:
        align = "right"
    elif abs((x0 + x1) / 2 - 306) < 12 and width < 440 and x0 > 70:
        align = "center"
    for it in items:
        h = inline(it["spans"], page, size)
        if not h.strip():
            continue
        out.append(dict(base, kind="li" if it["li"] else "p", html=h, align=align,
                        end=clean(it["spans"][-1]["text"]).rstrip(), y1=y1))
    return out


def render_image(page, bbox, img_dir, img_url, name, counter):
    r = fitz.Rect(bbox) & page.rect
    if r.width < 8 or r.height < 8:
        return None
    small = r.width < 80 and r.height < 80
    pix = page.get_pixmap(clip=r, dpi=200 if small else 150)
    ext = "png" if small else "jpg"
    fn = "%s-%03d.%s" % (name, counter, ext)
    if small:
        pix.save(os.path.join(img_dir, fn))
    else:
        pix.save(os.path.join(img_dir, fn), jpg_quality=82)
    return "%s/%s" % (img_url, fn), r


def page_elements(page, pno, img_dir, img_url, counter):
    els = []
    d = page.p.get_text("dict")
    # Terminal output with box-drawing tables cannot be shown as text: render its frame as a picture.
    regions = []
    for b in d["blocks"]:
        if b["type"] or b["bbox"][1] >= FOOTER_Y:
            continue
        text = "".join(s["text"] for l in b["lines"] for s in l["spans"])
        mono = sum(len(s["text"]) for l in b["lines"] for s in l["spans"] if is_code(s["font"]))
        if re.search("[─-╿]", text) and mono > 0.3 * len(text):
            r = fitz.Rect(b["bbox"])
            for br, _ in page.boxes:
                if br.contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
                    r = br
                    break
            for q in regions:
                if q.intersects(r):
                    q |= r
                    break
            else:
                regions.append(r + (-3, -3, 3, 3))
    for r in regions:
        counter[0] += 1
        src, rr = render_image(page.p, r, img_dir, img_url, "img", counter[0])
        els.append(dict(kind="img", src=src, bbox=tuple(rr), x0=rr.x0, pno=pno, box=(), size=0, term=True))
    for b in d["blocks"]:
        if b["bbox"][1] >= FOOTER_Y:
            continue
        c = fitz.Rect(b["bbox"])
        if any(q.contains(fitz.Point((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2)) for q in regions):
            continue
        if b["type"] == 1:
            counter[0] += 1
            res = render_image(page.p, b["bbox"], img_dir, img_url, "img", counter[0])
            if res:
                src, r = res
                els.append(dict(kind="img", src=src, bbox=tuple(r), x0=r.x0, pno=pno,
                                box=(), size=0))
        else:
            els.extend(convert_block(b, page, pno))
    # Images that sit beside text come before that text (so they can float).
    els.sort(key=lambda e: (round(e["bbox"][1] - (24 if e["kind"] == "img" else 0)), e["bbox"][0]))
    return els


def merge(els):
    """Join paragraphs split by blocks or pages, and code blocks that follow each other."""
    out = []
    for e in els:
        prev = out[-1] if out else None
        if prev and prev["kind"] == "p" and e["kind"] == "p" and prev["box"] == e["box"] \
                and abs(prev["size"] - e["size"]) < 0.3 and abs(prev["x0"] - e["x0"]) < 3 \
                and not prev["end"].endswith(TERMINAL) and prev.get("align") == e.get("align") \
                and (e["pno"] != prev["pno"] or e["bbox"][1] - prev["y1"] < prev["size"]) \
                and e["html"][:1].islower():
            prev["html"] += " " + e["html"]
            prev["end"], prev["y1"] = e["end"], e["y1"]
            continue
        if prev and prev["kind"] == "code" and e["kind"] == "code" and prev["box"] == e["box"] \
                and e["pno"] == prev["pno"] and e["bbox"][1] - prev["y1"] < 3 * prev["lh"]:
            gap = int((e["bbox"][1] - prev["y1"]) / prev["lh"])
            prev["lines"] += [""] * gap + e["lines"]
            prev["y1"] = e["y1"]
            continue
        out.append(e)
    return out


def box_style(box):
    x0, y0, x1, y1, fill = box
    rgb = "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in fill[:3])
    small = (x1 - x0) < 260 and (y1 - y0) < 50
    dark = sum(fill[:3]) < 1.5
    cls = "ew-btn" if small else "ew-box"
    return cls, "background:%s;%s" % (rgb, "color:#fff;" if dark else "")


def indent(e):
    m = (e["x0"] - LEFT) * PX
    return m if m > 8 else 0


def element_html(e, anchors):
    k = e["kind"]
    fs = "font-size:%.0fpx;" % (e["size"] * PX) if e.get("size") else ""
    if k == "img":
        x0, y0, x1, y1 = e["bbox"]
        w = (x1 - x0) * PX
        cls = "ew-img"
        if x1 - x0 < 0.62 * (RIGHT - LEFT) and not e.get("term"):
            cls += " ew-left" if (x0 + x1) / 2 < 306 else " ew-right"
        return '<img class="%s" src="%s" alt="" loading="lazy" style="width:%.0fpx">' % (cls, e["src"], w)
    if k == "code":
        lines = e["lines"]
        while lines and not lines[-1].strip():
            lines.pop()
        return '<pre style="%s">%s</pre>' % (fs, esc("\n".join(lines)))
    if k in ("h1", "h2", "h3"):
        aid = anchors(e)
        text = e.get("text", "")
        style = fs + ("color:%s;" % TITLE_COLOR if k == "h1" else "")
        return '<%s id="%s" style="%s">%s</%s>' % (k, aid, style, text, k)
    style = fs
    if e.get("align"):
        style += "text-align:%s;" % e["align"]
    if indent(e) and k == "p":
        style += "margin-left:%.0fpx;" % indent(e)
    tag = "li" if k == "li" else "p"
    return '<%s style="%s">%s</%s>' % (tag, style, e["html"], tag)


def auto_full(doc, toc):
    """Pages shown as one picture: cover, contents, last page, adverts and greetings.
    These have light text on a dark background, or one picture over the whole page."""
    full = {1, len(doc)} | ({toc} if toc else set())
    for i, p in enumerate(doc, 1):
        area = p.rect.get_area()
        d = p.get_text("dict")["blocks"]
        img = sum((fitz.Rect(b["bbox"]) & p.rect).get_area() for b in d if b["type"] == 1)
        light_text = sum(len(s["text"].strip()) for b in d if b["type"] == 0
                         for l in b["lines"] for s in l["spans"] if s["color"] > 0xe0e0e0)
        if img > 0.95 * area or light_text > 60:
            full.add(i)
    return full


def build(args):
    doc = fitz.open(args.pdf)
    name = os.path.splitext(os.path.basename(args.pdf))[0]          # EmberWings-2025-02
    m = re.search(r"(\d{4})-0?(\d+)$", name)
    args.url = args.url or "/file/emberwings/%s.html" % name
    args.out = args.out or "site/content/extra/%s.html" % name.lower()
    args.img_url = args.img_url or "/file/emberwings/%s" % name
    args.img_dir = args.img_dir or "site/static" + args.img_url
    args.title = args.title or ("EmberWings %s/%s" % m.groups() if m else name)
    args.description = args.description or "%s: the quarterly magazine about Firebird" % args.title
    if not args.toc:
        links = [len([l for l in p.get_links() if l.get("page") is not None and not l.get("uri")]) for p in doc]
        args.toc = links.index(max(links)) + 1 if max(links) >= 5 else 0
    full = auto_full(doc, args.toc) if args.full == "auto" else {int(x) for x in args.full.split(",") if x}
    print("%s: contents page %s, pages as pictures %s" % (name, args.toc, sorted(full)))
    if os.path.isdir(args.img_dir):
        for f in os.listdir(args.img_dir):
            os.remove(os.path.join(args.img_dir, f))
    os.makedirs(args.img_dir, exist_ok=True)
    toc = {}
    if args.toc:
        tp = doc[args.toc - 1]
        words = tp.get_text("words")
        for l in tp.get_links():
            if l.get("page") is None or l.get("uri"):
                continue
            r = fitz.Rect(l["from"])
            label = " ".join(w[4] for w in words if fitz.Rect(w[:4]).intersects(r) and
                             abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < 5)
            toc[l["page"]] = (toc.get(l["page"], "") + " " + clean(label)).strip()
    els, counter = [], [0]
    for i, p in enumerate(doc):
        pno = i + 1
        if pno in full:
            counter[0] += 1
            src, r = render_image(p, p.rect, args.img_dir, args.img_url, "page", pno)
            links = []
            for l in p.get_links():
                lr = fitz.Rect(l["from"])
                href = l.get("uri") or ("@@PAGE%d@@" % l["page"] if l.get("page") is not None else None)
                if href:
                    links.append((href, lr.x0 / r.width, lr.y0 / r.height, lr.width / r.width, lr.height / r.height))
            els.append(dict(kind="img", src=src, bbox=tuple(r), x0=0, pno=pno, box=(), size=0, full=True,
                            links=links))
            continue
        pe = page_elements(Page(p), pno, args.img_dir, args.img_url, counter)
        # A big title in two text blocks is one title.
        k = 0
        while k < len(pe) - 1:
            a, b = pe[k], pe[k + 1]
            if a["kind"] == b["kind"] == "h1" and b["bbox"][1] - a["bbox"][3] < a["size"]:
                a["text"] += " " + b["text"]
                a["bbox"] = (a["bbox"][0], a["bbox"][1], b["bbox"][2], b["bbox"][3])
                del pe[k + 1]
            else:
                k += 1
        # With a contents page, only the articles it lists are top level; other big titles are sections.
        if toc:
            first = True
            for e in pe:
                if e["kind"] == "h1":
                    if i not in toc or not first:
                        e["kind"] = "h2"
                    first = False
        if i in toc and not any(e["kind"] == "h1" for e in pe):
            pe.insert(0, dict(kind="h1", text=esc(toc[i]), bbox=(LEFT, 0, RIGHT, 0), x0=LEFT,
                              pno=pno, box=(), size=24))
        # A title page has the picture above the title: put the title first (menu links land on it).
        if len(pe) > 1 and pe[0]["kind"] == "img" and pe[1]["kind"] == "h1":
            pe[0], pe[1] = pe[1], pe[0]
        for e in pe:
            if e["kind"] == "h1" and i in toc:
                e["menu"] = toc[i]
        els.extend(pe)
    els = merge(els)

    used = {}

    def anchors(e):
        base = re.sub(r"<[^>]+>", "", e.get("text", ""))
        slug = re.sub(r"[^a-z0-9]+", "-", html.unescape(base).lower()).strip("-")[:50] or "s"
        used[slug] = used.get(slug, 0) + 1
        e["id"] = slug if used[slug] == 1 else "%s-%d" % (slug, used[slug])
        return e["id"]

    body, stack, in_list = [], [], False
    for e in els:
        chain = e.get("box", ())
        if e["kind"] != "li" and in_list:
            body.append("</ul>")
            in_list = False
        # close boxes that end, open new ones
        n = 0
        while n < len(stack) and n < len(chain) and stack[n] == chain[n]:
            n += 1
        if in_list and len(stack) != n:
            body.append("</ul>")
            in_list = False
        while len(stack) > n:
            stack.pop()
            body.append("</div>")
        for b in chain[n:]:
            cls, st = box_style(b)
            body.append('<div class="%s" style="%s">' % (cls, st))
            stack.append(b)
        if e["kind"] == "li" and not in_list:
            st = "margin-left:%.0fpx;" % indent(e) if indent(e) > 30 else ""
            if re.match(r"(<[^>]+>)*\s*(\d+|[a-z])[.)]\s", e["html"]):
                st += "list-style:none;"   # the text already has the number
            body.append('<ul style="%s">' % st)
            in_list = True
        if e.get("full"):
            body.append('<div class="ew-page"><img src="%s" alt="Page %d" loading="lazy">' % (e["src"], e["pno"]))
            for href, x, y, w, h in e["links"]:
                body.append('<a href="%s" style="left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%"></a>'
                            % (html.escape(href), x * 100, y * 100, w * 100, h * 100))
            body.append("</div>")
        else:
            body.append(element_html(e, anchors))
    if in_list:
        body.append("</ul>")
    body.extend("</div>" for _ in stack)

    page_ids = {}
    for e in els:
        if e["kind"] == "h1" and "id" in e:
            page_ids.setdefault(e["pno"] - 1, e["id"])
    body = [re.sub(r"@@PAGE(\d+)@@", lambda m: "#" + page_ids.get(int(m.group(1)), ""), x) for x in body]

    # Menu: articles (h1) with their sections (h2).
    menu, open_sub = [], False
    for e in els:
        if e["kind"] == "h1":
            if open_sub:
                menu.append("</ul></li>")
            name = esc(e.get("menu") or html.unescape(re.sub(r"<[^>]+>", "", e["text"])))
            menu.append('<li class="ew-art"><a href="#%s">%s</a><ul>' % (e["id"], name))
            open_sub = True
        elif e["kind"] == "h2" and open_sub:
            name = html.unescape(re.sub(r"<[^>]+>", "", e["text"])).strip()
            name = esc(name if len(name) < 70 else name[:67] + "...")
            menu.append('<li><a href="#%s">%s</a></li>' % (e["id"], name))
    if open_sub:
        menu.append("</ul></li>")

    title = args.title
    pdf_url = args.url[:-5] + ".pdf"
    fm = "\n".join([
        "---",
        'title: "Firebird: %s"' % title,
        'html_title: "Firebird: %s"' % title,
        'description: "%s"' % args.description,
        'og_title: "%s"' % title,
        'og_site_name: "%s"' % title,
        'source_url: ""',
        'url: "%s"' % args.url,
        "---",
    ])
    page = TEMPLATE % dict(fm=fm, url=args.url, title=esc(title), pdf=pdf_url,
                           menu="\n".join(menu), body="\n".join(body), css=CSS, js=JS)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("wrote %s (%d bytes), %d images" % (args.out, len(page), len(os.listdir(args.img_dir))))


CSS = """
.ew { display: flex; gap: 32px; max-width: 1080px; margin: 0 auto; padding: 32px 16px 80px;
  align-items: flex-start; font-family: Lato, "Segoe UI", Arial, sans-serif; color: #130101; }
.ew-nav { flex: 0 0 270px; position: sticky; top: 16px; max-height: calc(100vh - 32px);
  overflow-y: auto; font-size: 15px; line-height: 1.35; border-right: 1px solid #e6e3db; padding-right: 12px; }
.ew-nav .ew-issue { font-family: "Bitter", Georgia, serif; font-size: 22px; color: #7d3c98; margin: 0 0 4px; }
.ew-nav .ew-pdf { display: inline-block; margin: 0 0 14px; font-size: 14px; }
.ew-nav ul { list-style: none; margin: 0; padding: 0; }
.ew-nav li { margin: 0; }
.ew-nav a { display: block; color: #130101; text-decoration: none; padding: 4px 8px; border-radius: 4px; }
.ew-nav a:hover { background: #f3efe6; }
.ew-nav .ew-art > a { font-weight: 700; margin-top: 6px; }
.ew-nav .ew-art ul { display: none; padding-left: 10px; font-size: 13.5px; }
.ew-nav .ew-art.open ul, .ew-nojs .ew-nav .ew-art ul { display: block; }
.ew-nav a.active { background: #93223a; color: #fff; }
.ew-main { flex: 1 1 auto; min-width: 0; max-width: 730px; line-height: 1.45; }
.ew-main p { margin: 0 0 10px; text-align: justify; hyphens: auto; }
.ew-main h1 { font-family: "Bitter", Georgia, serif; font-weight: 300; margin: 48px 0 18px;
  clear: both; padding-top: 24px; border-top: 3px solid #93223a; line-height: 1.2; }
.ew-main h2 { font-weight: 700; margin: 26px 0 10px; clear: both; line-height: 1.25; }
.ew-main h3 { font-weight: 700; margin: 16px 0 6px; line-height: 1.3; }
.ew-main h1, .ew-main h2, .ew-main h3 { scroll-margin-top: 16px; color: #130101; }
.ew-main h2, .ew-main h3, .ew-main p, .ew-main li { font-family: Lato, "Segoe UI", Arial, sans-serif; }
.ew-main a { color: #2b6cc4; }
.ew-main ul { margin: 0 0 10px 22px; padding: 0; }
.ew-main li { margin: 0 0 4px; }
.ew-main pre { background: #f8f8f8; border: 1px solid #e6e3db; padding: 10px 12px; overflow-x: auto;
  font-family: "Courier New", Consolas, monospace; line-height: 1.3; clear: both; white-space: pre; }
.ew-main code { font-family: "Courier New", Consolas, monospace; }
.ew-main pre code { font-size: inherit; }
.ew-img { max-width: 100%; height: auto; display: block; margin: 8px auto 14px; }
.ew-left { float: left; margin: 4px 18px 10px 0; max-width: 55%; }
.ew-right { float: right; margin: 4px 0 10px 18px; max-width: 55%; }
.ew-page { position: relative; max-width: 730px; margin: 0 0 24px; box-shadow: 0 1px 6px rgba(0,0,0,.18); }
.ew-page img { display: block; width: 100%; height: auto; }
.ew-page a { position: absolute; display: block; }
.ew-page a:hover { outline: 2px solid rgba(255,255,255,.7); background: rgba(255,255,255,.12); }
.ew-box { padding: 14px 18px; margin: 10px 0 14px; border-radius: 4px; overflow: hidden; }
.ew-box pre { background: transparent; border: 0; padding: 0; margin: 0; }
.ew-box p:last-child { margin-bottom: 0; }
.ew-btn { display: block; width: fit-content; margin: 10px auto; padding: 6px 18px; border-radius: 18px; }
.ew-btn p { margin: 0; text-align: center !important; }
.ew-btn a { color: inherit; text-decoration: none; }
.ew-box a { color: inherit; }
@media (max-width: 860px) {
  .ew { flex-direction: column; }
  .ew-nav { position: static; flex: none; width: 100%; max-height: none; border-right: 0;
    border-bottom: 1px solid #e6e3db; padding: 0 0 10px; }
  .ew-nav .ew-art ul { display: none !important; }
  .ew-left, .ew-right { float: none; max-width: 100%; margin: 8px auto; }
  .ew-main p { text-align: left; }
}
"""

JS = """
(function () {
  var root = document.querySelector('.ew');
  root.classList.remove('ew-nojs');
  var links = Array.prototype.slice.call(document.querySelectorAll('.ew-nav a[href^="#"]'));
  var heads = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); });
  function update() {
    var cur = 0;
    for (var i = 0; i < heads.length; i++) {
      if (heads[i] && heads[i].getBoundingClientRect().top < 120) cur = i;
    }
    links.forEach(function (a, i) {
      a.classList.toggle('active', i === cur);
    });
    var art = links[cur].closest('.ew-art');
    document.querySelectorAll('.ew-art').forEach(function (li) { li.classList.toggle('open', li === art); });
    var nav = document.querySelector('.ew-nav'), a = links[cur];
    if (a.offsetTop < nav.scrollTop || a.offsetTop > nav.scrollTop + nav.clientHeight - 40)
      nav.scrollTop = a.offsetTop - 80;
  }
  var t;
  window.addEventListener('scroll', function () { clearTimeout(t); t = setTimeout(update, 60); });
  update();
})();
"""

TEMPLATE = """%(fm)s
<!-- Generated by tools/pdf_magazine.py from %(pdf)s. Do not edit; run the tool again. -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bitter:wght@300&family=Lato:ital,wght@0,400;0,700;1,400&display=swap">
<style>%(css)s</style>
<section class="ew ew-nojs">
<nav class="ew-nav" aria-label="Contents">
<p class="ew-issue">%(title)s</p>
<a class="ew-pdf" href="%(pdf)s">Download PDF</a>
<ul>
%(menu)s
</ul>
</nav>
<article class="ew-main">
%(body)s
</article>
</section>
<script>%(js)s</script>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--url", help="default /file/emberwings/<PDF name>.html")
    ap.add_argument("--out", help="default site/content/extra/<pdf name>.html")
    ap.add_argument("--img-dir", help="default site/static/file/emberwings/<PDF name>")
    ap.add_argument("--img-url", help="default /file/emberwings/<PDF name>")
    ap.add_argument("--full", default="auto", help="page numbers, or auto")
    ap.add_argument("--toc", type=int, default=0, help="contents page; default: the page with most links")
    ap.add_argument("--title", help="default EmberWings YYYY/N")
    ap.add_argument("--description")
    a = ap.parse_args()
    for pdf in a.pdf:
        build(argparse.Namespace(**dict(vars(a), pdf=pdf)))
