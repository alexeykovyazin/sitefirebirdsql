#!/bin/bash
# Pull static files from origin (read-only rrsync). Stops if >2% of files would be deleted.
set -euo pipefail
# Origin address is kept out of the repo: /usr/local/etc/fb-sync.env sets ORIGIN_HOST and ORIGIN_PORT.
. /usr/local/etc/fb-sync.env
SRC=mirror@$ORIGIN_HOST:docroot
DST=/srv/firebirdsql/assets
SSH="ssh -p $ORIGIN_PORT -i /home/deploy/.ssh/id_origin_mirror -o StrictHostKeyChecking=accept-new"
DIRS="file img js template plugins"
# Not synced (unused): doclibs (in private/doclibs), book, doctools, security (PHP captcha), lst_files.
FILES="favicon.ico google27b5d15e48805187.html 404.html 50x.html"
OPTS=(-a --delete --exclude-from=/usr/local/etc/fb-assets-exclude.txt -e "$SSH")
total=$(find $DST -type f 2>/dev/null | wc -l)
del=0
for d in $DIRS; do
  n=$(rsync "${OPTS[@]}" -n --itemize-changes $SRC/$d/ $DST/$d/ 2>/dev/null | grep -c "^\*deleting" || true); del=$((del+n))
done
if [ "$total" -gt 0 ] && [ $((del*100/total)) -gt 2 ]; then echo "ABORT: $del of $total files would be deleted"; exit 3; fi
for d in $DIRS; do mkdir -p $DST/$d; rsync "${OPTS[@]}" $SRC/$d/ $DST/$d/; done
for f in $FILES; do rsync -a -e "$SSH" $SRC/$f $DST/$f; done
# 68854C93 (CMS banners): the banner list 68854C93.js, the banner folders it names (GetBanners() loads
# them on the home page and in the right column), and the image used by /en/firebird-performance-tour-2019.
# Old banners are in private/68854C93.
mkdir -p $DST/68854C93
rsync -a -e "$SSH" mirror@$ORIGIN_HOST:static/68854C93/68854C93.js $DST/68854C93/68854C93.js
# Skip CMS leftovers in banner folders: admin thumbnails (cms-*), old copies (_*), empty "none" files.
INC=(--exclude="/68854C93/*/cms-*" --exclude="/68854C93/*/_*" --exclude="/68854C93/*/none" --include=/68854C93/ --include=/68854C93/68854C93.js --include=/68854C93/performance-tour-2019/ --include=/68854C93/performance-tour-2019/performance-tour-2019.png)
for b in $(grep -oE "file[[:space:]]*:[[:space:]]*'[^']+'" $DST/68854C93/68854C93.js | sed -E "s/.*'([^']+)'/\1/"); do
  INC+=(--include="/68854C93/$b/" --include="/68854C93/$b/**")
done
rsync -a --delete --delete-excluded "${INC[@]}" --exclude="*" -e "$SSH" mirror@$ORIGIN_HOST:static/68854C93 $DST/
mkdir -p $DST/rss && rsync -a --exclude=/pt/ -e "$SSH" mirror@$ORIGIN_HOST:static/rss/ $DST/rss/  # /rss/pt/ redirects to the EN feed
ln -sfn file/documentation $DST/docs
cd $DST && find . -type f -printf "%P\t%s\n" | sort > /srv/firebirdsql/assets-manifest.tsv
echo "OK files=$(wc -l < /srv/firebirdsql/assets-manifest.tsv) size=$(du -sh $DST | cut -f1)"
