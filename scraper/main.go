// Command scraper crawls the firebirdsql.org CMS origin and writes
// raw/pages/** (HTML as served) and raw/inventory.csv.
//
// Usage: ORIGIN_URL=https://<origin host> go run ./scraper -out raw
package main

import (
	"crypto/sha256"
	"crypto/tls"
	"encoding/csv"
	"encoding/hex"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Paths served as plain files by nginx; they come from rsync, not from the crawler.
var assetPrefixes = []string{
	"/file/", "/img/", "/template/", "/css/", "/js/", "/plugins/", "/doclibs/",
	"/book/", "/security/", "/doctools/", "/lst_files/", "/static/", "/rss/", "/docs/", "/files/",
}

var assetExt = regexp.MustCompile(`(?i)\.(pdf|ico|gif|png|jpe?g|svg|webp|avi|js|css|mp4|flv|html?|swf|txt|bin|xml|zip|gz|7z|rar|exe|msi|tar|bz2|json|woff2?|ttf|eot|doc|docx|xls|xlsx|ppt|pptx|odt|chm)$`)

var siteHosts = map[string]bool{
	"firebirdsql.org": true, "www.firebirdsql.org": true, "cms.firebirdsql.org": true,
	"new.firebirdsql.org": true, "dfp.firebirdsql.org": true,
}

var (
	reHref  = regexp.MustCompile(`(?i)(?:href|src)\s*=\s*["']([^"'#]+)`)
	reTitle = regexp.MustCompile(`(?is)<title[^>]*>(.*?)</title>`)
	reLoc   = regexp.MustCompile(`(?i)<link>\s*([^<]+?)\s*</link>`)
)

type page struct {
	URL      string
	Status   int
	Location string
	Kind     string // page | asset | external
	Lang     string
	Format   string // new | legacy | unknown | as-is
	Title    string
	SHA      string
	Size     int
	LinksOut []string
	LinksIn  int
}

type crawler struct {
	base   *url.URL
	out    string
	client *http.Client
	mu     sync.Mutex
	pages  map[string]*page
	queue  chan string
	wg     sync.WaitGroup
	delay  time.Duration
	max    int
}

func main() {
	base := flag.String("base", os.Getenv("ORIGIN_URL"), "origin base URL (default: $ORIGIN_URL)")
	out := flag.String("out", "raw", "output directory")
	workers := flag.Int("workers", 3, "parallel workers")
	delay := flag.Duration("delay", 300*time.Millisecond, "delay per worker between requests")
	max := flag.Int("max", 20000, "max pages")
	flag.Parse()

	b, err := url.Parse(*base)
	if err != nil {
		log.Fatal(err)
	}
	c := &crawler{
		base: b, out: *out, delay: *delay, max: *max,
		pages: map[string]*page{},
		queue: make(chan string, 100000),
		client: &http.Client{
			Timeout: 60 * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, // Cloudflare Origin CA
				MaxIdleConnsPerHost: *workers,
			},
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}
	for _, s := range []string{"/", "/map", "/en/news", "/pt/news", "/en/", "/rss/en/news.xml", "/rss/pt/news.xml"} {
		c.enqueue(s)
	}
	for i := 0; i < *workers; i++ {
		go c.worker()
	}
	c.wg.Wait()
	close(c.queue)
	if err := c.writeInventory(); err != nil {
		log.Fatal(err)
	}
}

func isAsset(p string) bool {
	for _, pre := range assetPrefixes {
		if strings.HasPrefix(p, pre) {
			return true
		}
	}
	if strings.HasPrefix(p, "/rss/") {
		return false
	}
	return assetExt.MatchString(p)
}

// normalize returns a site-relative URL ("/path?query") or "" for external links.
func (c *crawler) normalize(ref, from string) (string, bool) {
	// Browsers drop TAB, CR and LF inside URLs (WHATWG URL spec); some CMS links contain them.
	ref = strings.NewReplacer("\t", "", "\r", "", "\n", "").Replace(strings.TrimSpace(ref))
	if ref == "" || strings.HasPrefix(ref, "mailto:") || strings.HasPrefix(ref, "javascript:") ||
		strings.HasPrefix(ref, "tel:") || strings.HasPrefix(ref, "data:") {
		return "", false
	}
	fu, err := url.Parse(from)
	if err != nil {
		return "", false
	}
	u, err := fu.Parse(ref)
	if err != nil {
		return "", false
	}
	if u.Scheme != "" && u.Scheme != "http" && u.Scheme != "https" {
		return "", false
	}
	if u.Host != "" && !siteHosts[strings.ToLower(u.Hostname())] && !(c.base != nil && strings.EqualFold(u.Hostname(), c.base.Hostname())) {
		return u.String(), false
	}
	p := u.EscapedPath()
	if p == "" {
		p = "/"
	}
	p = path.Clean(p) + map[bool]string{true: "/", false: ""}[strings.HasSuffix(u.Path, "/") && p != "/"]
	if p == "//" {
		p = "/"
	}
	if u.RawQuery != "" {
		p += "?" + u.RawQuery
	}
	return p, true
}

func (c *crawler) enqueue(p string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if pg, ok := c.pages[p]; ok {
		pg.LinksIn++
		return
	}
	pg := &page{URL: p, LinksIn: 1}
	c.pages[p] = pg
	switch {
	case strings.HasPrefix(p, "http"):
		pg.Kind = "external"
		return
	case isAsset(strings.SplitN(p, "?", 2)[0]):
		pg.Kind = "asset"
		pg.Format = "as-is"
		return
	case strings.HasPrefix(p, "/download-file?"):
		// Download interstitial: one template for all ?file= values; static site uses one JS page.
		pg.Kind = "download"
		pg.Format = "download"
		return
	}
	pg.Kind = "page"
	if len(c.pages) > c.max {
		return
	}
	c.wg.Add(1)
	c.queue <- p
}

func (c *crawler) worker() {
	for p := range c.queue {
		c.fetch(p)
		c.wg.Done()
		time.Sleep(c.delay)
	}
}

func (c *crawler) fetch(p string) {
	full := c.base.String() + p
	var resp *http.Response
	var err error
	for try := 0; try < 3; try++ {
		req, _ := http.NewRequest("GET", full, nil)
		req.Header.Set("User-Agent", "fb-static-mirror/1.0")
		resp, err = c.client.Do(req)
		if err == nil && resp.StatusCode < 500 {
			break
		}
		if err == nil {
			resp.Body.Close()
		}
		time.Sleep(time.Duration(try+1) * 2 * time.Second)
	}
	c.mu.Lock()
	pg := c.pages[p]
	c.mu.Unlock()
	if err != nil {
		log.Printf("ERR %s: %v", p, err)
		pg.Status = -1
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	pg.Status = resp.StatusCode
	pg.Size = len(body)
	sum := sha256.Sum256(body)
	pg.SHA = hex.EncodeToString(sum[:])
	if strings.HasPrefix(p, "/pt/") || p == "/pt" {
		pg.Lang = "pt"
	} else {
		pg.Lang = "en"
	}
	log.Printf("%d %s", resp.StatusCode, p)

	if resp.StatusCode >= 300 && resp.StatusCode < 400 {
		loc := resp.Header.Get("Location")
		if n, ok := c.normalize(loc, full); ok {
			pg.Location = n
			c.enqueue(n)
		} else {
			pg.Location = loc
		}
		return
	}
	if resp.StatusCode != 200 {
		return
	}
	ct := resp.Header.Get("Content-Type")
	html := string(body)
	if strings.Contains(ct, "xml") {
		pg.Format = "rss"
		for _, m := range reLoc.FindAllStringSubmatch(html, -1) {
			if n, ok := c.normalize(m[1], full); ok {
				c.enqueue(n)
			}
		}
		c.save(p, body, ".xml")
		return
	}
	if !strings.Contains(ct, "html") {
		pg.Format = "as-is"
		return
	}
	pg.Format = detectFormat(html)
	if m := reTitle.FindStringSubmatch(html); m != nil {
		pg.Title = strings.Join(strings.Fields(m[1]), " ")
	}
	seen := map[string]bool{}
	for _, m := range reHref.FindAllStringSubmatch(html, -1) {
		n, internal := c.normalize(m[1], full)
		if n == "" || seen[n] {
			continue
		}
		seen[n] = true
		pg.LinksOut = append(pg.LinksOut, n)
		_ = internal
		c.enqueue(n)
	}
	c.save(p, body, ".html")
}

func detectFormat(html string) string {
	switch {
	case strings.Contains(html, "/template/css/style.css") && strings.Contains(html, "header-area"):
		return "new"
	case strings.Contains(html, "/css/site.css") || strings.Contains(html, "content_menu"):
		return "legacy"
	}
	return "unknown"
}

// save writes the body to raw/pages/<path>/index.html (query string encoded in the name).
func (c *crawler) save(p string, body []byte, ext string) {
	name := strings.TrimSuffix(strings.SplitN(p, "?", 2)[0], "/")
	if q := strings.SplitN(p, "?", 2); len(q) == 2 {
		h := sha256.Sum256([]byte(q[1]))
		name += "/__q_" + hex.EncodeToString(h[:6])
	}
	f := filepath.Join(c.out, "pages", filepath.FromSlash(name), "index"+ext)
	if err := os.MkdirAll(filepath.Dir(f), 0o755); err != nil {
		log.Print(err)
		return
	}
	if err := os.WriteFile(f, body, 0o644); err != nil {
		log.Print(err)
	}
}

func (c *crawler) writeInventory() error {
	if err := os.MkdirAll(c.out, 0o755); err != nil {
		return err
	}
	f, err := os.Create(filepath.Join(c.out, "inventory.csv"))
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	w.Write([]string{"url", "status", "location", "kind", "lang", "format", "title", "size", "sha256", "links_in", "links_out"})
	keys := make([]string, 0, len(c.pages))
	for k := range c.pages {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	stats := map[string]int{}
	for _, k := range keys {
		p := c.pages[k]
		stats[p.Kind+"/"+p.Format+"/"+strconv.Itoa(p.Status)]++
		w.Write([]string{p.URL, strconv.Itoa(p.Status), p.Location, p.Kind, p.Lang, p.Format, p.Title,
			strconv.Itoa(p.Size), p.SHA, strconv.Itoa(p.LinksIn), strconv.Itoa(len(p.LinksOut))})
	}
	w.Flush()
	sk := make([]string, 0, len(stats))
	for k := range stats {
		sk = append(sk, k)
	}
	sort.Strings(sk)
	for _, k := range sk {
		fmt.Printf("%-40s %d\n", k, stats[k])
	}
	return w.Error()
}
