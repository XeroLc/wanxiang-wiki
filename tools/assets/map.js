/* 互动地图：平移、缩放、图层、信息卡。无外部依赖。 */
(function () {
  "use strict";

  var viewport = document.getElementById("mapViewport");
  var canvas = document.getElementById("mapCanvas");
  var svg = canvas ? canvas.querySelector(".map-svg") : null;
  var card = document.getElementById("mapCard");
  if (!viewport || !canvas || !svg) return;

  var BASE = 1500;
  var state = { k: 1, x: 0, y: 0 };
  var fitScale = 1;
  var interacted = false;
  var dragging = false;
  var moved = 0;
  var start = { x: 0, y: 0, px: 0, py: 0 };

  function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }

  function apply(animate) {
    if (animate) {
      canvas.classList.add("is-animating");
      window.setTimeout(function () { canvas.classList.remove("is-animating"); }, 460);
    }
    canvas.style.transform = "translate(" + state.x + "px," + state.y + "px) scale(" + state.k + ")";
    var zoomLabel = document.getElementById("zoomReset");
    if (zoomLabel) zoomLabel.textContent = Math.round(state.k * 100) + "%";
  }

  function fit() {
    var vw = viewport.clientWidth;
    var vh = viewport.clientHeight;
    fitScale = Math.min(vw / BASE, vh / BASE) * 0.94;
    state.k = fitScale;
    state.x = (vw - BASE * fitScale) / 2;
    state.y = (vh - BASE * fitScale) / 2;
    apply(false);
  }

  function clampPan() {
    var vw = viewport.clientWidth;
    var vh = viewport.clientHeight;
    var w = BASE * state.k;
    var h = BASE * state.k;
    var pad = 180;
    if (w <= vw) {
      state.x = (vw - w) / 2;
    } else {
      state.x = clamp(state.x, vw - w - pad, pad);
    }
    if (h <= vh) {
      state.y = (vh - h) / 2;
    } else {
      state.y = clamp(state.y, vh - h - pad, pad);
    }
  }

  function zoomAt(factor, px, py) {
    var next = clamp(state.k * factor, fitScale * 0.7, fitScale * 5);
    if (next === state.k) return;
    var ratio = next / state.k;
    state.x = px - (px - state.x) * ratio;
    state.y = py - (py - state.y) * ratio;
    state.k = next;
    clampPan();
    interacted = true;
    apply(false);
  }

  viewport.addEventListener("wheel", function (e) {
    e.preventDefault();
    var rect = viewport.getBoundingClientRect();
    var px = e.clientX - rect.left;
    var py = e.clientY - rect.top;
    var factor = Math.exp(-e.deltaY * 0.0012);
    zoomAt(factor, px, py);
  }, { passive: false });

  viewport.addEventListener("pointerdown", function (e) {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    dragging = true;
    moved = 0;
    start.x = state.x;
    start.y = state.y;
    start.px = e.clientX;
    start.py = e.clientY;
    viewport.classList.add("is-dragging");
    try { viewport.setPointerCapture(e.pointerId); } catch (err) { /* 降级 */ }
  });

  viewport.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    var dx = e.clientX - start.px;
    var dy = e.clientY - start.py;
    moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
    state.x = start.x + dx;
    state.y = start.y + dy;
    clampPan();
    apply(false);
  });

  function endDrag(e) {
    if (!dragging) return;
    dragging = false;
    viewport.classList.remove("is-dragging");
    if (moved > 6) interacted = true;
    try { viewport.releasePointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
  }
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);

  var zoomIn = document.getElementById("zoomIn");
  var zoomOut = document.getElementById("zoomOut");
  var zoomReset = document.getElementById("zoomReset");
  if (zoomIn) zoomIn.addEventListener("click", function () {
    zoomAt(1.25, viewport.clientWidth / 2, viewport.clientHeight / 2);
  });
  if (zoomOut) zoomOut.addEventListener("click", function () {
    zoomAt(0.8, viewport.clientWidth / 2, viewport.clientHeight / 2);
  });
  if (zoomReset) zoomReset.addEventListener("click", function () {
    interacted = false;
    fit();
  });

  viewport.addEventListener("dblclick", function () { interacted = false; fit(); });

  window.addEventListener("resize", function () {
    if (!interacted) fit();
    else clampPan(), apply(false);
  });

  /* ---------------- 图层 ---------------- */

  Array.prototype.forEach.call(document.querySelectorAll("[data-layer-toggle]"), function (input) {
    function sync() {
      svg.classList.toggle("hide-" + input.getAttribute("data-layer-toggle"), !input.checked);
    }
    input.addEventListener("change", sync);
    sync();
  });

  /* ---------------- 选中与信息卡 ---------------- */

  function clearActive() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".domain.is-active, .marker.is-active, .slot.is-active"),
      function (el) { el.classList.remove("is-active"); }
    );
    Array.prototype.forEach.call(
      document.querySelectorAll(".mi-item.is-active"),
      function (el) { el.classList.remove("is-active"); }
    );
  }

  function kindOf(el) {
    if (el.classList.contains("domain")) return "域";
    if (el.classList.contains("slot")) return "扩展槽";
    return "地标";
  }

  function show(el) {
    if (!card) return;
    clearActive();
    el.classList.add("is-active");
    var type = el.getAttribute("data-id") ? "域" : kindOf(el);
    var slug = el.getAttribute("data-slug") || "";
    var cx = parseFloat(el.getAttribute("data-cx") || "0");
    var cy = parseFloat(el.getAttribute("data-cy") || "0");
    var link = slug
      ? '<a class="mc-link" href="docs/' + slug + '">打开域志 →</a>'
      : '<span class="mc-link">未登记域</span>';

    card.innerHTML =
      '<p class="mc-kicker">' + type + " · 坐标 " + cx.toFixed(1) + ", " + cy.toFixed(1) + "</p>" +
      "<h2>" + el.getAttribute("data-name") + "</h2>" +
      '<p class="mc-sub">' + (el.getAttribute("data-sub") || "") + "</p>" +
      '<p class="mc-note">' + (el.getAttribute("data-note") || "") + "</p>" +
      '<div class="mc-foot"><span>' + (el.getAttribute("data-id") || "未登记") + "</span>" + link + "</div>";

    var idx = document.querySelector('.mi-item[data-target="' + el.getAttribute("data-id") + '"]');
    if (idx) idx.classList.add("is-active");
  }

  function centerOn(el) {
    var cx = parseFloat(el.getAttribute("data-cx") || "0");
    var cy = parseFloat(el.getAttribute("data-cy") || "0");
    var vw = viewport.clientWidth;
    var vh = viewport.clientHeight;
    if (state.k < fitScale * 1.12) state.k = fitScale * 1.35;
    state.x = vw / 2 - (150 + cx * 100) * state.k;
    state.y = vh / 2 - (150 + cy * 100) * state.k;
    interacted = true;
    clampPan();
    apply(true);
  }

  Array.prototype.forEach.call(document.querySelectorAll(".domain, .marker, .slot"), function (el) {
    el.addEventListener("click", function (e) {
      if (moved > 6) return;
      e.stopPropagation();
      show(el);
    });
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        show(el);
      }
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll(".mi-item"), function (btn) {
    btn.addEventListener("click", function () {
      var target = document.querySelector('[data-id="' + btn.getAttribute("data-target") + '"]');
      if (!target) return;
      show(target);
      centerOn(target);
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      clearActive();
      if (card) {
        card.innerHTML =
          '<p class="mc-kicker">点击地图</p><h2>万相界</h2>' +
          '<p class="mc-note">选择任意域、断界驿或扩展槽，查看详情。</p>';
      }
    }
  });

  fit();
})();
