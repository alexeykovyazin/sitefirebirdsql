// Site search for /en/search/: Fuse.js over /index.json (built by Hugo, layouts/index.json).
// Same approach as ib-aid.com.
(function () {
  var input = document.getElementById("q");
  var results = document.getElementById("search-results");
  if (!input || !results) return;

  var FUSE_URL = "https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js";
  var indexUrl = input.getAttribute("data-search-index") || "/index.json";
  var emptyText = input.getAttribute("data-empty") || "No results found.";
  var errorText = input.getAttribute("data-error") || "Could not load the search index.";
  var fuse = null;
  var timer = null;

  try {
    var q = new URLSearchParams(window.location.search).get("q");
    if (q) input.value = q;
  } catch (e) {}

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function highlight(text, query) {
    var safe = escapeHtml(text);
    if (!query) return safe;
    try {
      var rx = new RegExp("(" + escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      return safe.replace(rx, "<mark>$1</mark>");
    } catch (e) {
      return safe;
    }
  }

  function render(hits, query) {
    if (!hits.length) {
      results.innerHTML = "<p>" + escapeHtml(emptyText) + "</p>";
      return;
    }
    results.innerHTML = hits.slice(0, 30).map(function (hit) {
      var item = hit.item || hit;
      return '<a class="search-hit" href="' + escapeHtml(item.url) + '"><h3>' +
        highlight(item.title || "", query) + "</h3><p>" +
        highlight((item.summary || "").slice(0, 180), query) + "</p></a>";
    }).join("");
  }

  function ready() {
    if (fuse) return Promise.resolve();
    return loadScript(FUSE_URL)
      .then(function () { return fetch(indexUrl); })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        fuse = new Fuse(data, { keys: ["title", "summary", "content"], threshold: 0.35, ignoreLocation: true });
      });
  }

  function run() {
    var query = input.value.trim();
    if (!query) {
      results.innerHTML = "";
      return;
    }
    ready().then(function () {
      render(fuse.search(query), query);
    }).catch(function (e) {
      results.innerHTML = "<p>" + escapeHtml(errorText) + "</p>";
      console.error(e);
    });
  }

  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(run, 180);
  });
  if (input.value.trim()) run();
})();
