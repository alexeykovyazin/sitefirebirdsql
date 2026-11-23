"""Convert features.ods (crowdfunding feature list) into a JS data file.

Usage:
    python tools/crowdfunding_data.py E:/FF/features.ods site/static/file/crowdfunding/cf-data.js

Sheet layout (Sheet1):
    columns: Area | Feature | What it does | Status | Target | Budget | Received | From roadmap 6?
    "Adaptation and testing ..."         -> campaign 1 (release 5.5), one feature per row
    "Extra features on top of Firebird 6" -> campaign 2 (Firebird 6+), group rows + feature rows
    "ROADMAP"                             -> Firebird 6 roadmap, paid by current sponsors
"""
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
SQUARE_USD = 250


def read_rows(path):
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    table = next(root.iter(NS_T + "table"))
    rows = []
    for r in table.iter(NS_T + "table-row"):
        cells = []
        for c in r:
            if c.tag not in (NS_T + "table-cell", NS_T + "covered-table-cell"):
                continue
            n = min(int(c.get(NS_T + "number-columns-repeated", "1")), 20)
            txt = " ".join("".join(p.itertext()) for p in c.iter(NS_X + "p")).strip()
            cells += [txt or (c.get(NS_O + "value") or "")] * n
        cells = (cells + [""] * 8)[:8]
        if any(cells):
            rows.append([re.sub(r"\s+", " ", x).strip() for x in cells])
    return rows


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def money(s):
    s = s.replace(",", "").replace(" ", "")
    return int(float(s)) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def yes(s):
    return s.strip().lower() in ("y", "yes")


def split_issue(name):
    """'> - 7617 ANY_VALUE' -> ('#7617', 'ANY_VALUE')."""
    name = re.sub(r"^>\s*-\s*", "", name).strip()
    m = re.match(r"^(\d{3,5})\s+(.*)$", name)
    return ("#" + m.group(1), m.group(2)) if m else ("", name)


def feature(row, issue=""):
    i, name = split_issue(row[1])
    return {
        "issue": issue or i,
        "name": name,
        "what": row[2],
        "status": row[3],
        "target": row[4],
        "price": money(row[5]),
        "received": money(row[6]) or 0,
        "roadmap6": yes(row[7]),
    }


def main(src, dst):
    rows = read_rows(src)
    c1 = {"id": "fb55", "title": "Release Firebird 5.5 with the features below",
          "short": "Firebird 5.5", "note": "", "groups": []}
    c2 = {"id": "fb6", "title": "Support features you want to be in Firebird 6+",
          "short": "Firebird 6+", "note": "", "groups": []}
    roadmap, section, group, category = [], None, None, ""

    for row in rows[1:]:
        a, b = row[0], row[1]
        if a.startswith("Adaptation and testing"):
            section, c1["note"] = "c1", a
            continue
        if a.startswith("Extra features"):
            section, c2["note"], group = "c2", a, None
            continue
        if a == "ROADMAP":
            section = "rm"
            continue

        if section == "c1":
            g = next((x for x in c1["groups"] if x["name"] == a), None)
            if g is None:
                g = {"id": "fb55-" + slug(a), "name": a, "description": "", "groupPrice": None,
                     "received": 0, "features": []}
                c1["groups"].append(g)
            g["features"].append(feature(row))

        elif section == "c2":
            is_issue = a.startswith("#")
            if a and not is_issue:  # group header row
                group = {"id": "fb6-" + slug(a), "name": a, "description": b,
                         "groupPrice": money(row[5]), "received": money(row[6]) or 0, "features": []}
                c2["groups"].append(group)
            elif b and group is not None:
                group["features"].append(feature(row, issue=a if is_issue else ""))

        elif section == "rm":
            if not b and not a:
                continue
            if b and not row[3] and not a.startswith("#") and a != "n/a":
                category = a
                continue
            if a and not b and not row[3]:
                category = a
                continue
            roadmap.append({"issue": "" if a == "n/a" else a, "name": b, "status": row[3],
                            "target": row[4], "backport55": yes(row[5]), "category": category})

    for c in (c1, c2):
        for g in c["groups"]:
            priced = [f["price"] for f in g["features"] if f["price"]]
            g["goal"] = g["groupPrice"] or (sum(priced) or None)
            g["received"] = g["received"] or sum(f["received"] for f in g["features"])

    data = {"source": "features.ods", "generated": date.today().isoformat(),
            "squareUsd": SQUARE_USD, "campaigns": [c1, c2], "roadmap": roadmap}
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("/* Generated by tools/crowdfunding_data.py from features.ods. Do not edit. */\n")
        f.write("window.CF_DATA = ")
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    for c in (c1, c2):
        print(c["id"], [(g["name"], g["goal"], len(g["features"])) for g in c["groups"]])
    print("roadmap items:", len(roadmap))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
