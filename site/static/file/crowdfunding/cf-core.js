/* Crowdfunding test pages: shared state and helpers.
   Payments are simulated. Pledges are kept only in this browser (localStorage). */
(function () {
  "use strict";
  var D = window.CF_DATA;
  var SQ = D.squareUsd;
  var KEY = "cf-test-v1";
  var state = { pledges: [], seq: 0, lastBatch: 0 };
  var cart = {};
  var listeners = [];
  var groups = [];
  var byId = {};
  var roadmapByIssue = {};

  D.campaigns.forEach(function (c) {
    c.groups.forEach(function (g) {
      g.campaign = c;
      g.squares = g.goal ? Math.ceil(g.goal / SQ) : 0;
      groups.push(g);
      byId[g.id] = g;
    });
  });
  D.roadmap.forEach(function (r) {
    (r.issue || "").split(/[,\s]+/).forEach(function (i) { if (i) roadmapByIssue[i] = r; });
    if (!r.category) r.category = "Major features";
  });

  function load() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY));
      if (s && Array.isArray(s.pledges)) state = s;
    } catch (e) { /* storage blocked: start empty */ }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }
  function emit(kind, info) { listeners.forEach(function (f) { f(kind, info); }); }

  function pledgesFor(id) { return state.pledges.filter(function (p) { return p.groupId === id; }); }
  function baseSquares(g) { return Math.min(g.squares, Math.floor((g.received || 0) / SQ)); }
  function funded(g) {
    var n = baseSquares(g);
    pledgesFor(g.id).forEach(function (p) { n += p.squares; });
    return Math.min(n, g.squares);
  }
  function free(g) { return g.squares - funded(g); }

  /* One entry per funded square, in fill order. */
  function owners(g) {
    var out = [];
    var b = baseSquares(g);
    for (var i = 0; i < b; i++) out.push({ name: "Earlier sponsors", mine: false, batch: 0 });
    pledgesFor(g.id).forEach(function (p) {
      for (var k = 0; k < p.squares && out.length < g.squares; k++) {
        out.push({ name: p.show ? p.sponsor : "Anonymous sponsor", mine: !!p.mine, batch: p.batch, demo: !!p.demo });
      }
    });
    return out;
  }

  function sponsorsOf(g) {
    var map = {};
    var order = [];
    if (baseSquares(g)) { map["Earlier sponsors"] = { name: "Earlier sponsors", usd: baseSquares(g) * SQ }; order.push("Earlier sponsors"); }
    pledgesFor(g.id).forEach(function (p) {
      var name = p.show ? p.sponsor : "Anonymous sponsor";
      if (!map[name]) { map[name] = { name: name, usd: 0, mine: false }; order.push(name); }
      map[name].usd += p.squares * SQ;
      map[name].mine = map[name].mine || !!p.mine;
    });
    return order.map(function (n) { return map[n]; });
  }

  function setCart(id, n) {
    var g = byId[id];
    if (!g) return;
    n = Math.max(0, Math.min(n | 0, free(g)));
    if (n) cart[id] = n; else delete cart[id];
    emit("cart", { id: id });
  }
  function cartItems() {
    return groups.filter(function (g) { return cart[g.id]; }).map(function (g) {
      return { group: g, squares: cart[g.id], usd: cart[g.id] * SQ };
    });
  }
  function cartTotal() {
    return cartItems().reduce(function (a, it) { a.squares += it.squares; a.usd += it.usd; return a; }, { squares: 0, usd: 0 });
  }
  function clearCart() { cart = {}; emit("cart", {}); }

  function checkout(sponsor) {
    var items = cartItems();
    var batch = ++state.seq;
    items.forEach(function (it) {
      var n = Math.min(it.squares, free(it.group));
      if (n > 0) {
        state.pledges.push({ groupId: it.group.id, squares: n, sponsor: sponsor.name, show: sponsor.show !== false,
          method: sponsor.method || "", mine: true, batch: batch, at: Date.now() });
      }
    });
    state.lastBatch = batch;
    cart = {};
    save();
    emit("pledge", { batch: batch, items: items });
    return items;
  }

  function addDemo() {
    var batch = ++state.seq;
    var n = 1;
    groups.forEach(function (g) {
      if (!g.squares || Math.random() < 0.35) return;
      var parts = 1 + Math.floor(Math.random() * 3);
      for (var i = 0; i < parts; i++) {
        var room = free(g);
        if (room <= 0) return;
        var take = Math.max(1, Math.min(room, Math.round(g.squares * (0.04 + Math.random() * 0.16))));
        state.pledges.push({ groupId: g.id, squares: take, sponsor: "Demo sponsor " + (n++), show: Math.random() > 0.15,
          mine: false, demo: true, batch: batch, at: Date.now() });
      }
    });
    state.lastBatch = batch;
    Object.keys(cart).forEach(function (id) { setCartSilent(id); });
    save();
    emit("pledge", { batch: batch, demo: true });
  }
  function setCartSilent(id) {
    var g = byId[id];
    var n = Math.min(cart[id], free(g));
    if (n) cart[id] = n; else delete cart[id];
  }

  function reset() {
    state = { pledges: [], seq: 0, lastBatch: 0 };
    cart = {};
    save();
    emit("reset", {});
  }

  function campaignTotals(c) {
    var t = { goal: 0, raised: 0, groups: 0, features: 0, sponsors: 0 };
    var names = {};
    c.groups.forEach(function (g) {
      t.features += g.features.length;
      if (!g.squares) return;
      t.groups++;
      t.goal += g.goal;
      t.raised += Math.min(g.goal, funded(g) * SQ);
      pledgesFor(g.id).forEach(function (p) { names[p.show ? p.sponsor : "anon-" + p.batch] = 1; });
    });
    t.sponsors = Object.keys(names).length;
    return t;
  }
  function allTotals() {
    var t = { goal: 0, raised: 0, sponsors: 0 };
    var names = {};
    groups.forEach(function (g) {
      if (!g.squares) return;
      t.goal += g.goal;
      t.raised += Math.min(g.goal, funded(g) * SQ);
    });
    state.pledges.forEach(function (p) { names[p.show ? p.sponsor : "anon-" + p.batch] = 1; });
    t.sponsors = Object.keys(names).length;
    return t;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }
  function usd(n) { return "$" + Math.round(n).toLocaleString("en-US"); }
  function issueLinks(s) {
    if (!s) return "";
    return s.split(/[,\s]+/).filter(Boolean).map(function (i) {
      var num = i.replace("#", "");
      return /^\d+$/.test(num)
        ? '<a href="https://github.com/FirebirdSQL/firebird/issues/' + num + '" target="_blank" rel="noopener">#' + num + "</a>"
        : esc(i);
    }).join(", ");
  }
  function statusKind(s) {
    s = (s || "").toLowerCase();
    if (s.indexOf("built") === 0 || s === "completed") return "done";
    if (s.indexOf("experimental") === 0) return "exp";
    if (s.indexOf("process") >= 0 || s.indexOf("progress") >= 0 || s.indexOf("review") >= 0 || s.indexOf("pending") >= 0) return "wip";
    return "plan";
  }

  load();

  window.CF = {
    data: D, SQ: SQ, groups: groups, byId: byId, roadmapByIssue: roadmapByIssue,
    funded: funded, free: free, owners: owners, sponsorsOf: sponsorsOf,
    cart: function (id) { return cart[id] || 0; },
    setCart: setCart, cartItems: cartItems, cartTotal: cartTotal, clearCart: clearCart,
    checkout: checkout, addDemo: addDemo, reset: reset,
    lastBatch: function () { return state.lastBatch; },
    campaignTotals: campaignTotals, allTotals: allTotals,
    on: function (f) { listeners.push(f); },
    esc: esc, usd: usd, issueLinks: issueLinks, statusKind: statusKind
  };
})();
