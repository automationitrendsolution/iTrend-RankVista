/* Loading skeletons and chart hover interactions. Layered on top of rankvista.js. */
(function ($) {
  "use strict";

  var RV = (window.RV = window.RV || {});

  /* ------------------------------------------------------- skeletons */
  function skeletonHtml(kind) {
    var tpl = document.getElementById("rv-skeleton-" + kind);
    return tpl ? tpl.innerHTML : "";
  }

  function targetFor(element) {
    var selector = element.getAttribute("hx-target");
    if (!selector) return null;
    try {
      return document.querySelector(selector);
    } catch (e) {
      return null;
    }
  }

  function showSkeleton(element) {
    var kind = element.getAttribute("data-rv-skeleton");
    var target = targetFor(element);
    if (!kind || !target) return;
    var html = skeletonHtml(kind);
    if (html) {
      target.innerHTML = html;
    } else {
      target.classList.add("rv-swapping");
    }
  }

  function initSkeletons() {
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var source = event.detail && event.detail.elt;
      if (!source) return;

      if (source.hasAttribute("data-rv-skeleton")) {
        showSkeleton(source);
        return;
      }
      // Forms and pagination fall back to a dimmed target plus the progress bar.
      var target = targetFor(source);
      if (target) target.classList.add("rv-swapping");
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      var target = event.detail && event.detail.target;
      if (!target) return;
      // A boosted swap replaces the body, so components must be rebuilt.
      if (target === document.body && window.RV) {
        if (RV.enhanceSelects) RV.enhanceSelects(document);
        if (RV.scanValidation) RV.scanValidation(document);
        if (RV.startClock) RV.startClock();
      }
      target.classList.remove("rv-swapping");
      target.classList.add("rv-swapped-in");
      window.setTimeout(function () {
        target.classList.remove("rv-swapped-in");
      }, 220);
      initCharts();
    });

    document.body.addEventListener("htmx:responseError", function (event) {
      var target = event.detail && event.detail.target;
      if (target) target.classList.remove("rv-swapping");
    });
  }

  /* --------------------------------------------------- progress bar */
  function initProgressBar() {
    var bar = null;
    document.body.addEventListener("htmx:beforeRequest", function () {
      if (bar) return;
      bar = document.createElement("div");
      bar.className = "rv-loading-bar";
      document.body.appendChild(bar);
    });
    ["htmx:afterRequest", "htmx:responseError", "htmx:sendError"].forEach(function (name) {
      document.body.addEventListener(name, function () {
        if (bar) {
          bar.remove();
          bar = null;
        }
      });
    });
  }

  /* -------------------------------------------------- chart tooltip */
  function tooltipEl() {
    var el = document.getElementById("rv-tooltip");
    if (!el) {
      el = document.createElement("div");
      el.id = "rv-tooltip";
      el.className = "rv-tooltip";
      el.setAttribute("role", "tooltip");
      document.body.appendChild(el);
    }
    return el;
  }

  RV.showTooltip = function (html, x, y) {
    var el = tooltipEl();
    el.innerHTML = html;
    el.classList.add("is-visible");
    var rect = el.getBoundingClientRect();
    var left = x - rect.width / 2;
    var top = y - rect.height - 12;
    left = Math.max(8, Math.min(left, window.innerWidth - rect.width - 8));
    if (top < 8) top = y + 18;
    el.style.left = left + "px";
    el.style.top = top + "px";
  };

  RV.hideTooltip = function () {
    var el = document.getElementById("rv-tooltip");
    if (el) el.classList.remove("is-visible");
  };

  /* -------------------------------------------- sparkline hover */
  function initSparkline(chart) {
    var payload = chart.getAttribute("data-points");
    if (!payload) return;

    var points;
    try {
      points = JSON.parse(payload);
    } catch (e) {
      return;
    }
    if (!points.length) return;

    var svg = chart.querySelector("svg");
    if (!svg) return;

    var marker = svg.querySelector(".rv-spark__marker");
    if (!marker) {
      marker = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      marker.setAttribute("class", "rv-spark__marker");
      marker.setAttribute("r", "3.5");
      svg.appendChild(marker);
    }
    var rule = svg.querySelector(".rv-spark__rule");
    if (!rule) {
      rule = document.createElementNS("http://www.w3.org/2000/svg", "line");
      rule.setAttribute("class", "rv-spark__rule");
      rule.setAttribute("y1", "0");
      rule.setAttribute("y2", "64");
      svg.appendChild(rule);
    }

    var unit = chart.getAttribute("data-unit") || "";
    var label = chart.getAttribute("data-label") || "";

    function onMove(event) {
      var box = svg.getBoundingClientRect();
      // The viewBox is a fixed 240 units wide; map the pointer into that space.
      var ratio = (event.clientX - box.left) / box.width;
      var vx = Math.max(0, Math.min(240, ratio * 240));

      var nearest = points[0];
      var best = Infinity;
      for (var i = 0; i < points.length; i++) {
        var distance = Math.abs(points[i].x - vx);
        if (distance < best) {
          best = distance;
          nearest = points[i];
        }
      }

      marker.setAttribute("cx", nearest.x);
      marker.setAttribute("cy", nearest.y);
      marker.classList.add("is-visible");
      rule.setAttribute("x1", nearest.x);
      rule.setAttribute("x2", nearest.x);
      rule.classList.add("is-visible");

      RV.showTooltip(
        '<span class="rv-tooltip__date">' + nearest.date + "</span>" +
          '<span class="rv-tooltip__value">' + label + " " + nearest.value + unit + "</span>",
        box.left + (nearest.x / 240) * box.width,
        box.top + (nearest.y / 64) * box.height
      );
    }

    function onLeave() {
      marker.classList.remove("is-visible");
      rule.classList.remove("is-visible");
      RV.hideTooltip();
    }

    chart.addEventListener("mousemove", onMove);
    chart.addEventListener("mouseleave", onLeave);
    chart.setAttribute("data-rv-bound", "1");
  }

  /* ----------------------------------------- distribution hover */
  function initDistribution(column) {
    var payload = column.getAttribute("data-buckets");
    if (!payload) return;

    column.addEventListener("mouseenter", function () {
      var buckets;
      try {
        buckets = JSON.parse(payload);
      } catch (e) {
        return;
      }
      var rows = buckets
        .map(function (bucket) {
          return (
            '<span class="rv-tooltip__row"><i class="rv-dist__dot rv-dist__seg--' +
            bucket.tone +
            '"></i>' +
            bucket.label +
            '<b>' + bucket.count + "</b></span>"
          );
        })
        .join("");
      var box = column.getBoundingClientRect();
      RV.showTooltip(
        '<span class="rv-tooltip__date">' + column.getAttribute("data-date") + "</span>" + rows,
        box.left + box.width / 2,
        box.top
      );
    });

    column.addEventListener("mouseleave", RV.hideTooltip);
    column.setAttribute("data-rv-bound", "1");
  }

  /* ------------------------------------------------ matrix cells */
  function initMatrixHover(scope) {
    var root = scope || document;
    root.querySelectorAll(".rv-cell[data-tip]").forEach(function (cell) {
      if (cell.getAttribute("data-rv-bound")) return;
      cell.addEventListener("mouseenter", function () {
        var box = cell.getBoundingClientRect();
        RV.showTooltip(cell.getAttribute("data-tip"), box.left + box.width / 2, box.top);
      });
      cell.addEventListener("mouseleave", RV.hideTooltip);
      cell.setAttribute("data-rv-bound", "1");
    });
  }

  /* ------------------------------------------- rows per page */
  function initPageSize() {
    // Each option holds the full query string, so changing size keeps every filter.
    $(document).on("change", "[data-rv-page-size]", function () {
      var url = this.options[this.selectedIndex].dataset.url;
      if (!url) return;
      var target = this.getAttribute("data-rv-target");
      if (!target || !window.htmx) {
        window.location.href = url;
        return;
      }
      var kind = this.getAttribute("data-rv-skeleton");
      var node = document.querySelector(target);
      if (node && kind) {
        var html = skeletonHtml(kind);
        if (html) node.innerHTML = html;
      }
      window.htmx.ajax("GET", url, { target: target, swap: "innerHTML" }).then(function () {
        window.history.pushState({}, "", url);
      });
    });
  }

  function initCharts(scope) {
    var root = scope || document;
    root.querySelectorAll(".rv-kpi__chart[data-points]").forEach(function (chart) {
      if (!chart.getAttribute("data-rv-bound")) initSparkline(chart);
    });
    root.querySelectorAll(".rv-dist__col[data-buckets]").forEach(function (column) {
      if (!column.getAttribute("data-rv-bound")) initDistribution(column);
    });
    initMatrixHover(root);
  }

  RV.initCharts = initCharts;

  $(function () {
    initSkeletons();
    initProgressBar();
    initPageSize();
    initCharts();
  });
})(window.jQuery);
