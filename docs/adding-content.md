# Adding content by hand

Three examples: a news item, a new Jaybird version, a new Firebird release.
After each change, check it locally and deploy (see [README](../README.md)):

```
cd site
hugo server --config hugo.toml,hugo.local.toml
```

```
python converter/convert.py          # transition period only
cd site && hugo --quiet -d ../public && cd ..
HOST=$DROPLET_HOST ./deploy/deploy.sh
```

## Where to edit

The site has two modes (see [README](../README.md#two-modes-now-and-after-the-final-conversion)):
the **transition period** (now, the old CMS is still the source) and the time **after the final conversion**
(git is the only source). Most files are the same in both modes:

| Folder | What | In both modes |
|---|---|---|
| `site/content/news/*.md` | news in Markdown | edit directly |
| `site/content/extra/*.html` | new HTML pages (not from the CMS) | edit directly |
| `site/layouts/` | header, menu, footer | edit directly |

Only pages that came from the CMS (`site/content/pages/`) are different:

| Task | Transition period (now) | After the final conversion |
|---|---|---|
| Change a CMS page `<file>.html` | edit `converter/manual/<file>.html` (first copy it from `site/content/pages/` if it is not there) | edit `site/content/pages/<file>.html` |
| Change a text in all pages | add a row to `converter/global-replace.tsv` | search and replace in `site/content/pages/` |
| Make the change active | run `python converter/convert.py` | nothing: Hugo reads the file |
| `site/content/pages/` | **do not edit**: the converter writes it again on each run | normal content |

In the examples below, "edit the CMS page `<file>.html`" means the file from this table.

A standalone HTML article (own `<html>`, `<style>`, no site menu) gets the site header, menu and footer this way.
The URL stays the same:

```
python tools/wrap_article.py article.html /file/articles/<name>.html site/content/extra/<name>.html
```

Add `/articles/<name>.html` to `deploy/assets-exclude.txt`, so the sync does not copy the old file.
Example: `/file/articles/firebird-qa-en.html`.

An EmberWings PDF gets an HTML copy next to it (same name, `.html`), with a left menu of articles.
Pictures go to `site/static/file/emberwings/<name>/`. Needs `pip install pymupdf`.
The contents page, the pages shown as one picture (cover, contents, adverts) and the title
are found automatically; `--toc`, `--full` and `--title` change them.

```
python tools/pdf_magazine.py EmberWings-2026-03.pdf
```

Large files (zip, pdf, images for `/file/...` and `/img/...`) are not in git.
In the transition period, put them on the origin server into the same folder; the daily sync copies them to the droplet.
After the final conversion, put them directly on the droplet in `/srv/firebirdsql/assets/` (same folder).
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

2. **Downloads page** `/en/jdbc-driver/`. Edit the CMS page `en-jdbc-driver.html`
   (see [Where to edit](#where-to-edit)). In the "Jaybird 6.0.7" block, change the version, the GitHub link and the text:

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

4. Run the converter (transition period only), check locally, deploy.

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
   the CMS page `en-firebird-5-0.html`. The old page `/en/firebird-5-0-4/` stays as the archive.

3. **Other pages with the version.** Edit the CMS pages `en-downloads.html` (`/en/downloads/`)
   and `en-server-packages.html` (`/en/server-packages/`). Find the lines:

   ```
   grep -n "5\.0\.4" site/content/pages/en-downloads.html site/content/pages/en-server-packages.html
   ```

4. **"Popular" box on all pages.** It links to the latest release. Change this text in all pages:

   ```
   old: href="/en/firebird-5-0-4">Firebird 5.0.4<
   new: href="/en/firebird-5-0-5">Firebird 5.0.5<
   ```

   - Transition period: add a row to `converter/global-replace.tsv` (columns are separated by a TAB):

     ```
     old	new	note
     href="/en/firebird-5-0-4">Firebird 5.0.4<	href="/en/firebird-5-0-5">Firebird 5.0.5<	latest release in Popular box
     ```

   - After the final conversion: replace the text in the files directly:

     ```
     grep -rl 'href="/en/firebird-5-0-4">Firebird 5.0.4<' site/content | xargs sed -i 's|href="/en/firebird-5-0-4">Firebird 5.0.4<|href="/en/firebird-5-0-5">Firebird 5.0.5<|g'
     ```

5. **News.** Create `site/content/news/firebird-5-0-5-released.md` as in example 1, with a link to `/en/firebird-5-0-5/`.

6. Run the converter (transition period only), check locally, deploy.

## 4. Crowdfunding page (/foundation/features/)

Page: `site/content/extra/foundation-features.html`, URL `/foundation/features/`.
Payments are simulated; pledges are kept only in the browser (localStorage).
The "Propose your feature" form has no server part: it opens the visitor's email program
with a message to `foundation@firebirdsql.org` (address: `FF_MAIL` in the page script).
Sponsor logos: `site/static/file/crowdfunding/img/` (copies of `private/img/community/ff_logo_*.svg`).

1. Update the feature list from the spreadsheet:

   ```
   python tools/crowdfunding_data.py E:/FF/features.ods site/static/file/crowdfunding/cf-data.js
   ```

2. Preview: `cd site && hugo server --config hugo.toml,hugo.local.toml`,
   then open http://localhost:1313/foundation/features/.

Shared logic (cart, pledges, totals) is in `site/static/file/crowdfunding/cf-core.js`.

## 5. HQbird page (/hqbird)

The page is made from the content block in the dochqbird project
(`website/firebirdsql-hqbird/content.html` and `img/*.png`):

```
python tools/hqbird_page.py E:/Projects_2026/dochqbird/website/firebirdsql-hqbird
```

It writes `converter/manual/hqbird.html` and `site/content/pages/hqbird.html` (both modes work), and copies the
screenshots to `site/static/img/shop/hqbird/2027/`.
The user guide PDF (`/img/shop/hqbird/hqbird-2027-userguide.pdf`) is not in git: put it on the origin server.
