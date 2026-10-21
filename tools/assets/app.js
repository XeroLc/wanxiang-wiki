/* =========================================================
   万象客栈 · 设定集交互
   仅依赖 DOM 与 localStorage，无外部请求，可 file:// 直接打开
   ========================================================= */
(function () {
  "use strict";

  var docRoot = document.body.getAttribute("data-doc-root") || "";
  var THEME_KEY = "wx-theme";
  var SEARCH_LIMIT = 24;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---------------- 主题 ---------------- */

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* 隐私模式降级 */ }
    var btn = $("#themeBtn");
    if (btn) btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }

  var themeBtn = $("#themeBtn");
  if (themeBtn) {
    themeBtn.setAttribute("aria-pressed", currentTheme() === "dark" ? "true" : "false");
    themeBtn.addEventListener("click", function () {
      setTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  /* ---------------- 移动端目录 ---------------- */

  var menuBtn = $("#menuBtn");
  var scrim = $("#sidebarScrim");

  function closeNav() { document.body.classList.remove("nav-open"); }
  function toggleNav() { document.body.classList.toggle("nav-open"); }

  if (menuBtn) menuBtn.addEventListener("click", toggleNav);
  if (scrim) scrim.addEventListener("click", closeNav);
  $$(".nav-item").forEach(function (a) { a.addEventListener("click", closeNav); });

  /* ---------------- 阅读进度 ---------------- */

  var progress = $("#readingProgress");
  function updateProgress() {
    if (!progress) return;
    var doc = document.documentElement;
    var max = doc.scrollHeight - window.innerHeight;
    var ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    progress.style.width = (ratio * 100).toFixed(2) + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();

  /* ---------------- 目录高亮 ---------------- */

  var tocLinks = $$(".toc-item a");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var linkByHash = {};
    tocLinks.forEach(function (a) { linkByHash[a.getAttribute("href")] = a; });

    var headings = tocLinks.map(function (a) {
      var id = a.getAttribute("href").slice(1);
      return document.getElementById(id);
    }).filter(Boolean);

    function activate(id) {
      tocLinks.forEach(function (a) { a.parentNode.classList.remove("is-active"); });
      var link = linkByHash["#" + id];
      if (link) link.parentNode.classList.add("is-active");
    }

    var visible = new Set();
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) visible.add(entry.target.id);
        else visible.delete(entry.target.id);
      });
      if (visible.size) {
        var first = headings.filter(function (h) { return visible.has(h.id); })[0];
        if (first) activate(first.id);
      }
    }, { rootMargin: "-76px 0px -70% 0px", threshold: 0 });

    headings.forEach(function (h) { observer.observe(h); });
  }

  var tocTop = $(".toc-top");
  if (tocTop) {
    tocTop.addEventListener("click", function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  /* ---------------- 搜索 ---------------- */

  var modal = $("#searchModal");
  var input = $("#searchInput");
  var resultsEl = $("#searchResults");
  var triggers = [$("#searchTrigger"), $("#searchTriggerHero")].filter(Boolean);
  var index = Array.isArray(window.__SEARCH_INDEX__) ? window.__SEARCH_INDEX__ : [];
  var selected = -1;
  var currentResults = [];

  function openSearch() {
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    setTimeout(function () { if (input) input.focus(); }, 10);
  }

  function closeSearch() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    selected = -1;
  }

  triggers.forEach(function (btn) { btn.addEventListener("click", openSearch); });
  $$("[data-close-search]").forEach(function (el) { el.addEventListener("click", closeSearch); });

  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    var typing = tag === "INPUT" || tag === "TEXTAREA" || (e.target && e.target.isContentEditable);

    if (e.key === "/" && !typing) { if (!modal) return; e.preventDefault(); openSearch(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { if (!modal) return; e.preventDefault(); openSearch(); return; }
    if (e.key === "Escape") { closeSearch(); closeNav(); return; }
    if (!modal || !modal.classList.contains("is-open")) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      moveSelection(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      moveSelection(-1);
    } else if (e.key === "Enter") {
      if (currentResults.length && selected >= 0) {
        e.preventDefault();
        window.location.href = docRoot + currentResults[selected].url;
      }
    }
  });

  function moveSelection(delta) {
    var items = $$(".search-item", resultsEl);
    if (!items.length) return;
    selected = (selected + delta + items.length) % items.length;
    items.forEach(function (el, i) { el.classList.toggle("is-selected", i === selected); });
    items[selected].scrollIntoView({ block: "nearest" });
  }

  function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function score(doc, q) {
    var title = doc.title.toLowerCase();
    var subtitle = (doc.subtitle || "").toLowerCase();
    var text = (doc.text || "").toLowerCase();
    var s = 0;
    if (title === q) s += 200;
    if (title.indexOf(q) !== -1) s += 120;
    if (subtitle.indexOf(q) !== -1) s += 40;
    var pos = text.indexOf(q);
    if (pos !== -1) s += 10 + Math.max(0, 8 - Math.floor(pos / 400));
    try {
      var hits = text.match(new RegExp(escapeRegExp(q), "g"));
      if (hits) s += Math.min(40, hits.length * 2);
    } catch (e) { /* 忽略非法正则 */ }
    return s;
  }

  function snippet(doc, q) {
    var text = doc.text || "";
    var lower = text.toLowerCase();
    var pos = lower.indexOf(q);
    if (pos === -1) return escapeHtml(text.slice(0, 96)) + (text.length > 96 ? "…" : "");
    var start = Math.max(0, pos - 36);
    var piece = text.slice(start, start + 120);
    var prefix = start > 0 ? "…" : "";
    var suffix = start + 120 < text.length ? "…" : "";
    return prefix + highlight(piece, q) + suffix;
  }

  function highlight(text, q) {
    var safe = escapeHtml(text);
    if (!q) return safe;
    var safeQ = escapeHtml(q);
    try {
      var re = new RegExp("(" + escapeRegExp(safeQ) + ")", "gi");
      return safe.replace(re, "<mark>$1</mark>");
    } catch (e) {
      return safe;
    }
  }

  function renderResults(q) {
    if (!resultsEl) return;
    q = q.trim();
    if (!q) {
      resultsEl.innerHTML = '<div class="search-empty">输入关键词，检索全部 ' + index.length + " 篇设定</div>";
      currentResults = [];
      selected = -1;
      return;
    }
    var query = q.toLowerCase();
    var matched = index
      .map(function (doc) { return { doc: doc, s: score(doc, query) }; })
      .filter(function (item) { return item.s > 0; })
      .sort(function (a, b) { return b.s - a.s; })
      .slice(0, SEARCH_LIMIT)
      .map(function (item) { return item.doc; });

    currentResults = matched;
    selected = matched.length ? 0 : -1;

    if (!matched.length) {
      resultsEl.innerHTML = '<div class="search-empty">没有找到「' + escapeHtml(q) + "」，换个词试试</div>";
      return;
    }

    resultsEl.innerHTML = matched.map(function (doc, i) {
      return '<a class="search-item' + (i === 0 ? " is-selected" : "") + '" href="' + docRoot + doc.url + '">' +
        '<span class="search-item-head">' +
        '<span class="search-item-title">' + highlight(doc.title, q) + "</span>" +
        '<span class="search-item-group">' + escapeHtml(doc.group) + "</span>" +
        "</span>" +
        '<span class="search-item-snippet">' + snippet(doc, query) + "</span>" +
        "</a>";
    }).join("");
  }

  if (input) {
    input.addEventListener("input", function () { renderResults(input.value); });
    input.addEventListener("keydown", function (e) {
      // 输入法组合期间不触发回车跳转
      if (e.isComposing || e.keyCode === 229) return;
    });
  }
  renderResults("");

  /* ---------------- 标题锚点（复制链接的轻量替代） ---------------- */

  $$(".markdown-body h2[id], .markdown-body h3[id]").forEach(function (h) {
    h.style.cursor = "pointer";
    h.setAttribute("title", "点击复制本节链接");
    h.addEventListener("click", function (e) {
      if (e.target.closest("a")) return;
      var url = window.location.href.split("#")[0] + "#" + h.id;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () {
          var tip = document.createElement("span");
          tip.textContent = "链接已复制";
          tip.style.cssText =
            "position:fixed;left:50%;bottom:32px;transform:translateX(-50%);" +
            "background:var(--ink);color:var(--paper);padding:7px 14px;border-radius:6px;" +
            "font-size:12px;z-index:200;opacity:.95;transition:opacity .3s";
          document.body.appendChild(tip);
          setTimeout(function () { tip.style.opacity = "0"; }, 1100);
          setTimeout(function () { tip.remove(); }, 1500);
        }).catch(function () {});
      }
      window.history.replaceState(null, "", "#" + h.id);
    });
  });
})();
