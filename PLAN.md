# Plan: firebirdsql.org → static Hugo site + dynamic modules

Date: 2026-11-21 (version 2, after review). Source: origin `$ORIGIN_URL` (direct access to origin, without Cloudflare; the address is kept outside the repository).

## Status (2026-11-21)

| What | State |
|---|---|
| Droplet `fb-web-1` (ams3, s-1vcpu-1gb) | Created. Reserved IP `$DROPLET_HOST`, firewall `fb-web-fw` (22 — only from the administrator IP) |
| User `mirror` on origin (`rrsync -ro`) | Created, key from the droplet |
| Assets (rsync) | 1.4 GB, 12 616 files in `/srv/firebirdsql/assets`; script `deploy/fb-sync-assets.sh` |
| Crawler | 1354 en + 948 pt pages, 2 legacy, 31 CMS redirects; `raw/inventory.csv` |
| Converter + theme | 1224 unique pages, 1002 redirects (`_redirects.map`), `/download-file` in JS |
| Origin nginx rules for documentation | `docs_redirects.conf` copied as is |
| URL check on the droplet | All 200 pages → 200 or 301 to the canonical URL; 11 files 404 — also broken on origin |
| CMS database | Found: alias `fbsite7` → `/var/fb/fbsite7.fdb30` (1 GB). Not needed yet: HTML covers all pages |
| Not done | DNS `newtest` + TLS, Playwright comparison, Pagefind, CI and daily sync, monitoring, backups |

## 0. Goal and acceptance criteria

**Goal:** replace the PHP CMS with a static Hugo site that looks like the current site, plus several dynamic modules in Go.

**The site is ready (release R1) when:**
- every URL from the inventory table returns 200 or 301 (no 404);
- the visual difference from the original is ≤ 2 % on reference pages (new format);
- legacy pages are shown in the new design;
- all `/file/` files are in place, and SHA-256 matches origin;
- 0 broken internal links;
- service files in the root work (RSS, SendPulse, Google verification, robots).

## 1. Facts (checked 2026-11-21)

| Fact | What it means for the plan |
|---|---|
| CMS: `FireWeb engine v 4.1 FBSQL edition`, PHP 7.4-FPM, Firebird 3.0 on the same server (listens only on `[::1]:3050`) | Content comes from HTML; the CMS database is an extra source (the database file location is not found yet, see stage 2) |
| `cms.firebirdsql.org` and `firebirdsql.org` go through Cloudflare. Direct access: `$ORIGIN_URL` (nginx, 443). The certificate is a Cloudflare Origin CA | The crawler uses `$ORIGIN_URL` with TLS verification off (or with a trusted Origin CA). Port 80 is closed |
| SSH: `$ORIGIN_HOST`, port `$ORIGIN_PORT` (administrator). Ubuntu 22.04, disk 38 GB (56 % used) | Static folders are copied with **rsync**; for CI we create a separate read-only user (stage 0) |
| `www.firebirdsql.org` and `cms.firebirdsql.org` are **the same site**: the `www` docroot is made of symlinks to the `cms` docroot. Only `robots.txt` (www: `Allow: /`, cms: `Disallow: /`) and `/cms/` (admin panel, 404 on www) are different | One source. **Take `robots.txt` from www**, otherwise the new site drops out of search |
| Service files in the root: `favicon.ico`, `google27b5d15e48805187.html` (SendPulse), `68854C93`, `security/`, `rss/` → `static/rss/{en,pt}/news.xml`, `404.html`, `50x.html` | Move them to the same paths. The SendPulse service worker works only from the root. RSS: the same URL `/rss/en/news.xml` (subscribers); `/rss/pt/news.xml` → 301 to en |
| There is a Portuguese section: `/pt/news` → 200, `/pt/` → 404; no other languages | **pt is not moved** (decision 9). The crawler collects `/pt/...` URLs only for the redirect table: 301 to the English page or to `/en/news` |
| Static files on the server: `file/` **1.1 GB, 9482 files** (6404 html, 625 pdf, 1292 png, 125 zip, `.svn` garbage), `img/` 114 MB, `css/` 24 MB, `doclibs/` 26 MB, `template/` 13 MB, `js/` 4 MB, `plugins/` 3.6 MB, `book/` 3.3 MB | All of this is copied with rsync, as is. The crawler downloads only CMS HTML pages |
| **Two page formats.** New (`/`, `/en/firebird-5-0`): `/template/css/style.css`, `header-area`, `stellarnav`. Old (`/map`): `/css/site.css`, `bootstrap-grid`, `content_menu*`, often a path without `/en/` | The format is written to the URL table; legacy is converted to the new format (stage 3a) |
| Template: Bootstrap 4, **jQuery 1.12.4** (known XSS vulnerabilities), slick, stellarnav, magnific-popup, nice-select, Font Awesome 4 | In R1 we keep it as is, to look the same; the jQuery update is a separate task after R1 |
| No `sitemap.xml`; directory listing is closed (403) | Page URLs — by following links; files — rsync |
| No own forms: search through Google, push from SendPulse | Dynamic modules are new (R2+) |
| **Hosting: DigitalOcean**, droplet `s-1vcpu-1gb` — 1 vCPU, 1 GB RAM, 25 GB SSD, 1 TB traffic, $6/month. `fra1` does not have this size → region **`ams3`**. API token: local file `$DO_TOKEN_FILE` (checked: account is active, 0 droplets, limit 25). `doctl` is installed | Hugo/Pagefind build runs in CI, **not on the droplet**. Swap 2 GB. Assets of 1.3 GB fit. For heavy R3 modules — resize to `s-1vcpu-2gb` ($12) |

## 2. Architecture

```
origin $ORIGIN_HOST
  ├─ CMS HTML pages ───── crawler ──► raw/pages + inventory.csv
  └─ file/ img/ css/ … ── rsync ────► /srv/firebirdsql/assets (VM) and local
                                         │
raw/pages ── converter ──► site/content/**.md ── hugo + pagefind ──► public/

                ┌────────── nginx on the DigitalOcean droplet (no Cloudflare) ─┐
  browser ─────►│ /file/, /img/, /template/ … → /srv/firebirdsql/assets (alias) │
                │ /                            → public/ (current release)       │
                │ /api/<module>/…              → Go services (JSON, form POST)   │
                │ /en/<dyn-path>               → Go services (full HTML)         │
                └────────────────────────────────────────────────────────────────┘
```

### 2.1. URL rules
- URLs do not change. Both forms exist now: `/en/downloads/` (with a slash) and `/en/news` (without a slash).
- Hugo creates `path/index.html`. nginx: `try_files $uri $uri/index.html $uri.html =404;` — both forms work **without a redirect**.
- For each page, the table keeps the canonical URL form → `<link rel="canonical">` to `https://firebirdsql.org/...`.
- Pagination and query strings (`?page=2` etc.): the crawler normalizes them, the converter maps them to the Hugo scheme; old addresses → 301 in nginx (`map`).
- Absolute links to `firebirdsql.org`, `www.`, `cms.`, `cms-*.` in the content → relative.

### 2.2. Dynamic modules (Go + JS)

| Method | How it works | Example |
|---|---|---|
| **A. Form** | Static page + form; `POST /api/<module>` → JSON | Ask a question |
| **B. Island** | Static page; JS calls `GET /api/<module>/…` | Configuration calculator |
| **C. Dynamic page** | nginx sends the whole path to a Go service; the service renders HTML into the shell template | Trace and statistics analysis, exam demo |

Module list (decision 10):

| Module | Method | Path (draft) | Release |
|---|---|---|---|
| Ask a question | A | form on `/en/support/` and others, `POST /api/ask` | R2 |
| Configuration calculator | B | `/en/config-calculator`, `GET/POST /api/calc` | R3 |
| Firebird trace and statistics analysis tools | C | `/en/tools/trace/…`, `/en/tools/stat/…` | R3 |
| Certification exam demo | C | `/en/certification/exam-demo/…` | R3 |

- **Shell template:** Hugo builds `public/_shell/base.html` (the same `<head>`, header, menu, footer) with the markers `{{TITLE}}`, `{{META}}`, `{{CONTENT}}`. The services read it again after each deploy. The design changes in one place.
- **Registry** `site/data/dynamic.yaml` (module, method, paths, upstream) → nginx `location` blocks and fallback pages are generated from it.
- **Fallback:** service is not available → `error_page 502 503 504` → static page in the site design.
- **Security:** `Origin` check, `limit_req` in nginx, honeypot / hCaptcha (no Turnstile), validation on the server, size limit for attachments, secrets only in env.
- **Data:** where a database is needed — Firebird.
- **Services:** one Go binary with modules while there are ≤ 4 modules; separate services if there are more.

## 3. Releases

| Release | Content | Stages |
|---|---|---|
| **R1** | Static copy of the site on the new VM, DNS switch, sync with the CMS | 0–7 |
| **R2** | Framework for dynamic modules + "ask a question" form | 8 |
| **R3** | Calculator, trace/statistics analysis, exam demo; shop | 9 |
| **R4** | CMS freeze (1 month after R1), content only in Markdown | 10 |

Dynamic modules do not block R1. This way the static copy is released earlier.

## 4. Stages

Each stage has a **result** — the condition that closes the stage.

### Stage 0. Repository and infrastructure (1–2 days)
1. `git init`, GitHub repository, `.gitignore` (`raw/`, `public/`, assets).
2. **DigitalOcean droplet** `s-1vcpu-1gb`, region `ams3`, Ubuntu 24.04 LTS, name `fb-web-1`. Created by the script `deploy/do/create.sh` (`doctl compute droplet create … --user-data-file cloud-init.yaml --ssh-keys …`), so that the droplet can be created again. The token is read from `$DO_TOKEN_FILE` (or `DIGITALOCEAN_TOKEN` in CI secrets) and does not go into the repository.
   - New SSH key for the droplet → upload to DO (`doctl compute ssh-key import`).
   - **DO Cloud Firewall:** inbound 22 (only from your IPs), 80, 443; outbound — all.
   - Reserved IP (free while attached) — DNS points to it; the droplet can be re-created without a DNS change.
   - cloud-init: swap 2 GB, user `deploy`, SSH by key only, fail2ban, unattended-upgrades.
3. On the droplet: nginx, certbot, Docker (for R2+), folder `/srv/firebirdsql/{releases,assets}`. Hugo and Pagefind are **not installed** on the droplet — the build runs in CI, the droplet gets a ready `public/`.
4. **Test site `newtest.firebirdsql.org`** on the droplet (decision 12): the same nginx config, `X-Robots-Tag: noindex` and `robots.txt` with `Disallow: /` (only for newtest), basic auth if wanted.
   - Order: create the droplet → Reserved IP → you set up DNS `newtest` (A record, **without Cloudflare proxy**) → certbot issues the certificate → first deploy.
   - Before DNS, check by IP: `curl --resolve newtest.firebirdsql.org:80:<IP> http://newtest.firebirdsql.org/`.
   - Locally for development: `hugo server` and `docker compose up` (nginx + `public/` + assets + Go services).
5. On origin: user `mirror` with **read-only** access to the docroot (`rrsync -ro`), a separate key. The root key is not used in CI.

**Result:** `ssh mirror@origin` gives only read-only rsync; `https://newtest.firebirdsql.org/` opens with a valid certificate and `noindex`.

### Stage 1. Inventory (1–2 days)
1. **rsync of static files** (on the droplet, directly from origin; locally — in WSL, Git Bash on Windows has no rsync):
   `rsync -az --delete --exclude='.svn/' --exclude='*.svn-base' -e 'ssh -p $ORIGIN_PORT -i <key>' mirror@$ORIGIN_HOST:/var/www/cms.firebirdsql.org/docroot/{file,img,css,js,template,plugins,doclibs,book,security,doctools,lst_files} /srv/firebirdsql/assets/`
   plus the root service files and `static/rss/`.
   - Protection against an error on origin: first `--dry-run`; if > 2 % of files would be deleted — stop and notify.
   - Manifest `file-manifest.csv` (path, size, SHA-256) on both sides, compared.
2. **HTML crawler** (Go): starts from `/`, `/map`, RSS, and also `/pt/news` (only to collect pt URLs for redirects, pt content is not converted); follows all internal links (not only `/en/`). 2–4 requests/s, User-Agent `fb-static-mirror`. Also URLs from the Wayback Machine (`web.archive.org/cdx`) to find pages without incoming links.
   - The crawler does not download what rsync already has, but checks that each link to `/file/`, `/img/` etc. is in the manifest.
3. **Format detection** (`scraper/formats.yaml`): `new` (`/template/css/style.css` + `header-area`), `legacy` (`/css/site.css` or `content_menu`), `unknown` → manual review. Check the encoding of legacy pages.
4. The result is **`inventory.csv`**:

   | url | status | kind | lang | format | canonical | title | date | sha256 | links_in | links_out | target |
   |---|---|---|---|---|---|---|---|---|---|---|---|
   | `/en/firebird-5-0` | 200 | page | en | new | … | … | … | … | … | … | converted |
   | `/map` | 200 | page | en | legacy | … | … | … | … | … | … | redirect → … |
   | `/file/…/firebird-5-quickstartguide.pdf` | 200 | file | — | as-is | … | … | … | … | … | … | as-is |

   `kind`: page / file / asset / root-file; `format`: new / legacy / unknown / as-is; `target`: converted / redirect / manual / as-is.

**Result:** a report — number of pages by format and language, broken links, external links, pages without incoming links.

### Stage 2. Template analysis and data source (1–2 days)
1. Group pages by DOM structure: news, list, static page, product, download table, legacy.
2. Content selectors for each type → `scraper/selectors.yaml`.
3. **CMS database check (spike, strictly ≤ 0.5 day):** the database location is unknown (a search for `*.fdb` found nothing). Look for the connection string in the CMS code (`docroot/cms/`, `index.php` and included files), aliases in `/etc/firebird/3.0/databases.conf`, open files of the `firebird` process (`ls -l /proc/<pid>/fd`). If not found in 0.5 day or there is no access — **HTML only**. If found — take metadata from the database (dates, slug, menu order); page bodies still come from HTML.

**Result:** selectors cover 100 % of pages with status `new`/`legacy`; decision "HTML only" or "HTML + metadata from the database".

### Stage 3. Converter (2–3 days)
1. Front matter: `title`, `date`, `slug`, `url`, `lang`, `image`, `summary`, `description`, `type`, `weight`, `menu`, `aliases`.
2. Body: HTML → Markdown, complex blocks (download tables, tabs) — raw HTML (`markup.goldmark.renderer.unsafe = true`).
3. Keep `<title>`, `meta description`, OpenGraph from the original.
4. Menu and footer → `site/data/menu.yaml`, `footer.yaml`.
5. Idempotency: the same input → the same output. In the transition period, manual edits in `content/` are not allowed (the sync overwrites them); edits go to the CMS or to the converter.

**Result:** `hugo` builds the site without errors and warnings; the number of pages = the number of `converted` rows in `inventory.csv`.

### Stage 3a. Legacy → new format (2–4 days)
1. Legacy selectors: title, `content_menu_breadcrumbs`, `content_menu_nav`, body.
2. Take only the content; header, menu, CSS — from the new template.
3. Cleanup: inline styles, `bootstrap-grid` → Bootstrap 4 classes, lightbox → magnific-popup, FA5 (`fas fa-…`) → FA4 (`fa fa-…`) by a table.
4. A page in the new format exists → 301; does not exist → the same URL in the new design.
5. `target = manual` → list for manual review.
6. `/css/site.css` and `/plugins/` are needed only by `/file/` files (if they link to them) — Hugo pages do not include them.

**Result:** no Hugo page includes `/css/site.css`; the `manual` list is reviewed by a person.

### Stage 4. Hugo theme `fireweb` (3–4 days)
1. `baseof.html` — `<head>`, header, menu, footer from the original; original CSS/JS from assets.
2. Templates: home page (slider, blocks), news list + pagination as in the original, news single, default page, downloads, shop list.
3. Shortcodes: download button, tabs (`tab-min.js`), gallery, YouTube.
4. One language — en. Hugo multilingual mode is not enabled. `/pt/...` → 301 by the table (`target = redirect`), `/rss/pt/news.xml` → 301 to `/rss/en/news.xml`.
5. RSS at the old address `/rss/en/news.xml` (custom output format), `sitemap.xml`, `robots.txt` (from www + link to the sitemap), `404.html` in the site design.
6. Search: **Pagefind** over `public/` **and** over the `/file/` HTML documents (separate index, 6404 files) — otherwise the documentation drops out of search. Google search is the fallback.
7. Shell template `_shell/base.html` (needed for R2, we make it now — it costs almost nothing).

**Result:** all page types are rendered; Lighthouse is not worse than the original.

### Stage 5. Checks (2 days)
1. Playwright + `pixelmatch`: ~30 reference pages (new), widths 375 / 768 / 1440, threshold ≤ 2 %.
2. Legacy: comparison with a reference page of the new format (header, menu, footer).
3. `lychee` or `htmltest` over `public/` + assets: 0 broken internal links.
4. Each URL from `inventory.csv` on `newtest.firebirdsql.org` → 200 or 301.
5. SHA-256 manifest of assets on the VM = origin manifest.
6. SEO: canonical, `<title>`, description, 404 returns code 404, `robots.txt` allows indexing (only on production).

**Result:** all checks are green in CI; a report with diff images.

### Stage 6. Deployment and switch (1–2 days)
1. CI (GitHub Actions): `rsync assets → crawl → convert → hugo --minify → pagefind → stage 5 checks → deploy`.
2. Atomic deploy: `releases/<timestamp>` + switch of the `current` symlink; keep the last 5 releases; rollback = switch the symlink.
3. TLS: Let's Encrypt (certbot), auto-renewal, expiry monitoring.
4. DNS switch:
   - 2 days before, lower TTL to 300 s;
   - move `firebirdsql.org` and `www` from Cloudflare (proxy) to the droplet Reserved IP;
   - **rollback:** point DNS back to Cloudflare / the old server (do not turn off the old server before R4).
5. Monitoring: uptime (external service), 5xx in nginx logs, free disk space.
6. Backups: DO Backups (weekly, +$1.20/month) + a copy of `/srv/firebirdsql/assets` in **DO Spaces** (`rclone sync`, $5/month for 250 GB). After R4 this is the **only** copy of the files. Alternative to Spaces — keep a copy on the current origin server for free.
7. Load on 1 GB RAM: nginx serves static files (`sendfile`, `gzip_static` — compressed in advance in CI, `open_file_cache`, browser cache for `/file/`, `/img/`, `/template/`). DO monitoring agent: alerts CPU > 80 %, RAM > 85 %, disk > 80 %.

**Result:** production on the droplet, rollback tested on `newtest` before the DNS switch of the main domain.

### Stage 7. Transition period (CMS is the source), 1 month
1. Scheduled CI **once a day** (at night): the whole stage 6 pipeline. 1 month after R1 — stage 10.
2. Changes in `content/` after the sync — commit to git (edit history).
3. Checks failed → no deploy, notification.
4. Pages deleted in the CMS → deleted from `content/` + 301 or 410, as decided.

### Stage 8. R2 — dynamic module framework and forms (4–6 days)
1. `dynamic.yaml` → generator of nginx `location`, `limit_req`, `error_page`.
2. Go library `dyn/common`: shell render, JSON, validation, rate limit, SMTP, health check `/api/<module>/health`, JSON logs.
3. `docker-compose.yml`: locally nginx + static files + services; `hugo server` proxies `/api`.
4. **"Ask a question" module (A):**
   - Fields: name, e-mail, subject, Firebird version, OS, question text; consent to data processing.
   - `POST /api/ask` → e-mail to the support address (SMTP) + confirmation copy to the sender.
   - Protection: honeypot, hCaptcha, `limit_req` (for example 5 per minute per IP), `Origin` check, maximum 10 000 characters.
   - The form also works without JS (plain POST → "Thank you" page in the shell).

**Result:** the form works locally in `docker compose`; when the service is stopped, a fallback with an e-mail address is shown.

### Stage 9. R3 — Go modules (estimate after a specification for each module)
- **Configuration calculator (B)** — `/en/config-calculator`, `/api/calc`. Input: FB version 3/4/5, architecture (SuperServer / Classic / SuperClassic), RAM, CPU, number of connections, database size, page size. Output: `firebird.conf` / `databases.conf` (`DefaultDbCachePages`, `TempCacheLimit`, `LockHashSlots`, `FileSystemCacheThreshold` and others), "copy", "download .conf". Logic on the server.
- **Firebird trace and statistics analysis (C)** — the user uploads a trace log or `gstat` / monitoring output → Go parses it → HTML report in the shell (top queries by time, reads, frequency; tables and indexes).
  - Large file upload: streaming parsing, size limit (for example 200 MB, nginx `client_max_body_size`), compressed `.gz`/`.zip`.
  - **Privacy:** logs contain SQL and customer data. Do not keep files after parsing (or keep ≤ 24 h with deletion by timer), the report link is a random ID, a warning on the page.
  - Resources: job queue, CPU/RAM limit of the container, parsing timeout, no more than N jobs at the same time.
- **Certification exam demo (C)** — no registration: a random set of questions from the bank, timer, answers, result page with explanations.
  - Question bank — YAML in git or Firebird; demo questions are separate from the real exam.
  - Session state — signed cookie or a database record with TTL; protection against guessing — rate limit.
- **Shop:** until R3 — as now (static pages + payment links).

### Stage 10. R4 — move to Markdown (1–2 days)
1. Last sync, CMS is read-only.
2. Remove `crawl`/`convert` from CI; `site/content/` is the only source. Assets — only on the droplet + DO Spaces.
3. Instructions for authors: news, images, preview, PR → check → deploy.
4. `scraper/`, `converter/` stay in the repository as an archive. Turn off the old server 1 month after R4.

## 5. Repository structure

```
firebirdsql/
  scraper/          crawler (Go), formats.yaml, selectors.yaml
  converter/        HTML → Hugo content
  site/             Hugo: hugo.toml, content/, layouts/ (+ _shell), data/ (menu, dynamic.yaml)
  dyn/
    common/         shell render, JSON, validation, SMTP, rate limit
    ask/            ask a question (A, R2)
    calc/           configuration calculator (B, R3)
    analyzer/       trace and statistics analysis (C, R3)
    exam/           certification exam demo (C, R3)
  deploy/
    do/             create.sh (doctl), cloud-init.yaml, firewall
    nginx/          config (location blocks generated from dynamic.yaml)
    docker-compose.yml
  tests/visual/     Playwright + pixelmatch
  tests/dyn/        API and fallback tests
  .github/workflows/
  (not in git)      raw/, public/, /srv/firebirdsql/assets on the droplet (1.3 GB), DO token
```

## 6. Estimate

| Stage | Days |
|---|---|
| 0. Repository and infrastructure | 1–2 |
| 1. Inventory | 1–2 |
| 2. Template analysis + database spike | 1–2 |
| 3. Converter | 2–3 |
| 3a. Legacy | 2–4 |
| 4. Theme | 3–4 |
| 5. Checks | 2 |
| 6. Deployment | 1–2 |
| **R1 total (+20 % reserve)** | **16–25** |
| 8. R2 framework + ask a question | 3–5 |
| 10. R4 Markdown | 1–2 |
| 9. R3 calculator, analyzer, exam demo | after a specification for each module |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Without Cloudflare there is no DDoS protection and no CDN cache | Static files handle many requests; `limit_req`, DO Cloud Firewall; during an attack — quickly turn the Cloudflare proxy back on (DNS) |
| `robots.txt` copied from `cms.` (`Disallow: /`) | Take the file from www; check in stage 5 |
| rsync `--delete` deletes files if something breaks on origin | `--dry-run` + 2 % threshold + manifest |
| Root key in CI | User `mirror`, `rrsync -ro`, separate key |
| Many legacy pages | Estimate after stage 1; `manual` — by priority (traffic, incoming links) |
| After R4 the `/file/` files exist only on the droplet | DO Spaces + DO Backups until the old server is turned off |
| 1 GB RAM is not enough for R3 modules (analyzer, Firebird in Docker) | R1 static files and the R2 form fit; analyzer — 1 job at a time, streaming parsing; if not enough — resize the droplet to 2 GB (a few minutes of downtime) |
| Trace analyzer: logs contain SQL and customer data; large files load the droplet | Do not keep files, report by random ID, limits on size/CPU/time, queue |
| The DO token gives full access to the account | Keep it only in `E:\secure\` and in CI secrets; for CI — a separate token with minimal rights (scoped token) |
| The question form is a spam target | honeypot + hCaptcha + `limit_req` |
| jQuery 1.12.4 with vulnerabilities | A static site without user input — low risk; update after R1 |

## 8. Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Access to origin | `$ORIGIN_URL`, SSH `-p $ORIGIN_PORT` |
| 2 | `robots.txt` on `cms.` | Ignored by the crawler (our own site) |
| 3 | Dynamic parts | Web applications in Go, frontend in JS; the list — later |
| 4 | Calculator | Go application, later (R3) |
| 5 | Hosting | **DigitalOcean**, droplet `s-1vcpu-1gb`, `ams3`, nginx, Docker (replaces Hetzner) |
| 6 | Shop / payment | Later (R3), until then — as now |
| 7 | `/file/` files and other static files | rsync over SSH; the crawler only checks links |
| 8 | Content source | Transition period — CMS + sync; then — Markdown (R4) |
| 9 | Languages | Only **en**. `/pt/...` and `/rss/pt/news.xml` → 301 to English pages |
| 10 | Modules | Ask a question (A, R2); calculator (B), trace/statistics analysis (C), exam demo (C) — R3 |
| 11 | Transition period | 1 month, sync with the CMS once a day |
| 12 | Test site | **`newtest.firebirdsql.org`** on the DO droplet (DNS — after the droplet is created); locally — `hugo server` + `docker compose` |
| 13 | CMS database | Location unknown → spike ≤ 0.5 day, otherwise HTML only |

## 9. Open questions
1. E-mail address for the "Ask a question" form and the SMTP server for sending.
2. Specification for R3 modules: input file formats for the analyzer (trace API, `gstat -r`, MON$?), question bank for the exam demo, calculator formulas.
