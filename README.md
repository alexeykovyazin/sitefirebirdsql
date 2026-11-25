# firebirdsql.org static site

Static copy of https://firebirdsql.org, built with [Hugo](https://gohugo.io/).
Pages are converted from the old CMS (see [Two modes](#two-modes-now-and-after-the-final-conversion)). Large files (`/file`, `/img`, `/template`, `/js`)
are not in git: the server gets them from the origin by a daily rsync.

## Requirements

| Tool | Version | Used for |
|---|---|---|
| Hugo (extended) | 0.164 or newer | build and local server |
| Python | 3.10 or newer | theme download, converter, link check |
| Go | 1.24 or newer | crawler (only to crawl the CMS again) |

## Run the site locally

1. Get the code:

   ```
   git clone https://github.com/alexeykovyazin/sitefirebirdsql.git
   cd sitefirebirdsql
   ```

2. Download the theme files (CSS, JS, fonts, logo, about 5 MB) into `assets/`:

   ```
   python tools/fetch_assets.py
   ```

3. Start the Hugo server:

   ```
   cd site
   hugo server --config hugo.toml,hugo.local.toml
   ```

4. Open http://localhost:1313/en/start/

`hugo.local.toml` adds `../assets` as a second static folder. Hugo reloads the page when you change a file.

Pages show with styles, but images and documents inside pages (`/img/...`, `/file/...`)
are missing. To see them, copy the full asset folders (about 1 GB) into `assets/`
from the server (needs SSH access):

```
rsync -a root@$DROPLET_HOST:/srv/firebirdsql/assets/ assets/
```

## Build the site

```
cd site
hugo --quiet -d ../public
```

The result is in `public/`. nginx serves it, then the asset folders (see `deploy/nginx/`).

## Add news, a driver version or a release

See [docs/adding-content.md](docs/adding-content.md): news in Markdown, a new Jaybird version, a new Firebird release.

## Two modes: now and after the final conversion

The site works in two modes. The rules for editing pages are different.

| | **Transition period (now)** | **After the final conversion** |
|---|---|---|
| Source of the CMS pages | the old CMS, through `scraper/` + `converter/` | `site/content/` in git |
| Edit a CMS page | `converter/manual/<file>.html`, then run the converter | `site/content/pages/<file>.html` directly |
| `site/content/pages/` | written again on each converter run: **do not edit** | normal content: edit it |
| Text change in all pages | a row in `converter/global-replace.tsv` | search and replace in `site/content/pages/` |
| Large files (`/file/`, `/img/`) | put on the origin server, the daily sync copies them | put on the droplet (`/srv/firebirdsql/assets`) |
| `converter/`, `scraper/`, `raw/` | used | not used; we remove them (git history keeps them) |

In both modes, news in Markdown (`site/content/news/`), new HTML pages (`site/content/extra/`)
and layouts (`site/layouts/`) are edited directly.

The final conversion is stage R4 in [PLAN.md](PLAN.md): the last sync, then the CMS becomes read-only.
After it, `site/content/pages/` keeps the converter output with all manual copies applied.

## Change a page

Transition period:

- To change a CMS page, copy it to `converter/manual/<same file name>.html` and edit the copy.
  The converter uses the manual copy instead of the CMS version.
- Run the converter after the change. It needs the CMS crawl in `raw/` (not in git):

  ```
  ORIGIN_URL=https://<origin host> go run ./scraper -out raw
  python converter/convert.py
  ```

  The converter writes `site/content/pages/` and `site/static/_redirects.map` (nginx 301 map).

After the final conversion: edit `site/content/pages/<file>.html`. Do not run the converter.

Both modes:

- Redirects for removed or moved files: add a row to `deploy/removed-assets.tsv`.
- Layouts (header, footer, head): `site/layouts/`.

## Deploy

```
python converter/convert.py          # transition period only
cd site && hugo --quiet -d ../public && cd ..
HOST=$DROPLET_HOST ./deploy/deploy.sh
```

`deploy.sh` uploads `public/` as a new release and switches the `current` link. It keeps 5 releases.

## Check links and orphan files

On the server, after a deploy:

```
python3 /usr/local/bin/verify_site.py --site /srv/firebirdsql/current --assets /srv/firebirdsql/assets \
  --docs-redirects /etc/nginx/snippets/fb-docs-redirects.conf --manifest /srv/firebirdsql/assets-manifest.tsv --out /tmp/verify
```

Reports (broken links, orphan files and pages) are copied to `reports/verify/`.

## Folders

| Folder | Content |
|---|---|
| `site/` | Hugo site: content, layouts, static files |
| `converter/` | CMS to Hugo converter, hand-edited pages in `manual/` (transition period only) |
| `scraper/` | CMS crawler (transition period only) |
| `deploy/` | deploy and sync scripts, nginx config, droplet setup |
| `tools/` | link check, theme download |
| `docs/` | how to add news, driver versions, releases |
| `reports/verify/` | last link check reports |

Server addresses are not in the repo. Set `DROPLET_HOST`, `ORIGIN_URL` and `DO_TOKEN_FILE`
in your shell. On the server, `/usr/local/etc/fb-sync.env` sets `ORIGIN_HOST` and `ORIGIN_PORT`.
