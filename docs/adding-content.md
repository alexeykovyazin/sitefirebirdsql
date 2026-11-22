# Adding content by hand

Three examples: a news item, a new Jaybird version, a new Firebird release.
After each change, check it locally and deploy (see [README](../README.md)):

```
cd site
hugo server --config hugo.toml,hugo.local.toml
```

```
python converter/convert.py
cd site && hugo --quiet -d ../public && cd ..
HOST=$DROPLET_HOST ./deploy/deploy.sh
```

Where files go:

| Folder | What | Converter |
|---|---|---|
| `site/content/news/*.md` | new news in Markdown | not touched |
| `site/content/extra/*.html` | new HTML pages (not from the CMS) | not touched |
| `converter/manual/*.html` | changed copies of CMS pages | copied over `site/content/pages/` |
| `converter/global-replace.tsv` | text replacements in all pages | applied to every page |
| `site/content/pages/` | pages made by the converter | **do not edit**: rewritten on each run |

A standalone HTML article (own `<html>`, `<style>`, no site menu) gets the site header, menu and footer this way.
The URL stays the same:

```
python tools/wrap_article.py article.html /file/articles/<name>.html site/content/extra/<name>.html
```

Add `/articles/<name>.html` to `deploy/assets-exclude.txt`, so the sync does not copy the old file.
Example: `/file/articles/firebird-qa-en.html`.

An EmberWings PDF gets an HTML copy next to it (same name, `.html`), with a left menu of articles.
Pictures go to `site/static/file/emberwings/<name>/`. Needs `pip install pymupdf`.
`--full` lists pages shown as one picture (cover, contents, survey); `--toc` is the contents page.
In Git Bash, set `MSYS_NO_PATHCONV=1`, or it changes the `/file/...` arguments into Windows paths.

```
python tools/pdf_magazine.py EmberWings-2025-02.pdf /file/emberwings/EmberWings-2025-02.html \
  site/content/extra/emberwings-2025-02.html site/static/file/emberwings/EmberWings-2025-02 \
  /file/emberwings/EmberWings-2025-02 --full 1,2,4,76 --toc 4 --title "EmberWings 2025/2"
```

Large files (zip, pdf, images for `/file/...` and `/img/...`) are not in git.
Put them on the origin server into the same folder; the daily sync copies them to the droplet.
Release downloads are usually links to GitHub, so they need no upload.

## 1. Add a news item (Markdown)

Create `site/content/news/<name>.md`. The file name becomes the URL: `/en/news/<name>/`.

```markdown
---
title: "Firebird Conference 2027: call for papers"
date: 2026-12-01
summary: "Send your talk proposals before February 1, 2027."
---
The Firebird Conference 2027 takes place in Prague, **May 20-21, 2027**.

Send your talk proposals to the [Firebird Foundation](/en/firebird-foundation/).

![Conference hall](/img/news/2027/conference-hall.jpg)
```

Front matter fields:

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | page title and news heading |
| `date` | yes | news date, `YYYY-MM-DD`; newest news go first |
| `summary` | no | text in the news lists; default: start of the text |
| `image` | no | picture for the home page list; default: Firebird logo |
| `draft: true` | no | do not publish yet |

The news shows automatically:
- as a page at `/en/news/<name>/`;
- at the top of the list at `/en/news/`;
- at the top of the news block on the home page.

The RSS feed (`/rss/en/news.xml`) comes from the origin server and does not include Markdown news.

## 2. A new Jaybird version (example: Jaybird 6.0.8)

1. **News.** Create `site/content/news/jaybird-6-0-8-released.md`:

   ```markdown
   ---
   title: "Jaybird 6.0.8 released"
   date: 2026-12-15
   summary: "Jaybird 6.0.8 has been released"
   ---
   We are happy to announce the release of Jaybird 6.0.8, providing bug fixes.
   Jaybird is the Firebird JDBC driver.

   ## Changes

   - Fixed: ... ([#123](https://github.com/FirebirdSQL/jaybird/issues/123))

   Jaybird 6 supports Firebird 3.0, 4.0 and 5.0, on Java 17 and higher.

   See also:

   - [Jaybird 6 release notes](https://github.com/FirebirdSQL/jaybird/releases/tag/v6.0.8)
   - [Jaybird downloads](/en/jdbc-driver/)
   ```

2. **Downloads page** `/en/jdbc-driver/`. Edit `converter/manual/en-jdbc-driver.html`
   (if the file is not there, copy it from `site/content/pages/en-jdbc-driver.html` first).
   In the "Jaybird 6.0.7" block, change the version, the GitHub link and the text:

   ```html
   <td colspan="3"><span ...>Jaybird 6.0.8</span></td>
   ...
   <td><a download="" href="https://github.com/FirebirdSQL/jaybird/releases/download/v6.0.8/jaybird-6.0.8.zip">jaybird-6.0.8.zip</a></td>
   ...
   <p>Jaybird 6.0.8&nbsp;is the eighth maintenance release of Jaybird 6.</p>
   ...
   version: <code>6.0.8</code></p>
   ```

3. **Documentation (optional).** The release notes in `/docs/drivers/java/6.0.x/` are on the origin server
   (`file/documentation/drivers/java/6.0.x/`). Copy the new `release_notes.html` there, or link to GitHub as in the news above.

4. Run the converter, check locally, deploy.

## 3. A new Firebird release (example: Firebird 5.0.5)

1. **Release page** `/en/firebird-5-0-5/`. Copy the current page and change the URL line:

   ```
   cp site/content/pages/en-firebird-5-0.html site/content/extra/firebird-5-0-5.html
   ```

   In the front matter of the new file set:

   ```yaml
   title: "Firebird: Firebird 5.0.5"
   html_title: "Firebird: Firebird 5.0.5"
   og_site_name: "Firebird 5.0.5"
   source_url: ""
   url: "/en/firebird-5-0-5/"
   ```

   In the body, replace `5.0.4` with `5.0.5` in the file names, GitHub links, sizes and dates
   (for example `.../releases/download/v5.0.5/Firebird-5.0.5.xxxxx-0-windows-x64.exe`).

2. **Main page** `/en/firebird-5-0/` (always the latest 5.0.x). Make the same changes in
   `converter/manual/en-firebird-5-0.html`. The old page `/en/firebird-5-0-4/` stays as the archive.

3. **Other pages with the version.** Edit manual copies of `/en/downloads/` (`converter/manual/en-downloads.html`)
   and `/en/server-packages/` (`converter/manual/en-server-packages.html`). Find the lines:

   ```
   grep -n "5\.0\.4" site/content/pages/en-downloads.html site/content/pages/en-server-packages.html
   ```

4. **"Popular" box on all pages.** It links to the latest release. Add a row to
   `converter/global-replace.tsv` (columns are separated by a TAB):

   ```
   old	new	note
   href="/en/firebird-5-0-4">Firebird 5.0.4<	href="/en/firebird-5-0-5">Firebird 5.0.5<	latest release in Popular box
   ```

5. **News.** Create `site/content/news/firebird-5-0-5-released.md` as in example 1, with a link to `/en/firebird-5-0-5/`.

6. Run the converter, check locally, deploy.
