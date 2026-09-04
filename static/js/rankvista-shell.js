/* Theme switching, the IST clock, portalled dropdowns and button spinners. */
(function ($) {
  "use strict";

  var RV = (window.RV = window.RV || {});
  var THEME_KEY = "rv.theme";

  /* -------------------------------------------------------- theme */
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch (e) {
      /* private mode: the choice simply does not persist */
    }
    $("[data-rv-theme-toggle]").attr(
      "aria-label",
      theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
    );
  }

  function initTheme() {
    applyTheme(currentTheme());
    $(document).on("click", "[data-rv-theme-toggle]", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  /* -------------------------------------------------------- clock */
  var clockTimer = null;

  function initClock() {
    var nodes = document.querySelectorAll("[data-rv-clock-time]");
    if (!nodes.length) return;
    window.clearInterval(clockTimer);

    // Asia/Kolkata is resolved by the browser, so DST and offsets stay correct.
    var formatter = new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    });

    function tick() {
      var text = formatter.format(new Date()).toUpperCase();
      for (var i = 0; i < nodes.length; i++) {
        nodes[i].textContent = text;
      }
    }

    tick();
    clockTimer = window.setInterval(tick, 1000);
  }

  RV.startClock = initClock;

  /* ---------------------------------------------------- dropdowns */
  /* A menu inside a scroll container is clipped by its overflow. When one opens
     it is moved to <body> and positioned with fixed coordinates instead. */
  var portalled = null;

  function sweepOrphans() {
    // A swap can destroy the placeholder while the menu still sits on <body>.
    document.body.querySelectorAll(":scope > .rv-dropdown__menu--portal").forEach(function (menu) {
      if (!portalled || menu !== portalled.menu) menu.remove();
    });
  }

  function closePortal() {
    sweepOrphans();
    if (!portalled) return;
    if (!portalled.placeholder.isConnected) {
      portalled.menu.remove();
      portalled = null;
      return;
    }
    var menu = portalled.menu;
    menu.classList.remove("rv-dropdown__menu--portal");
    if (portalled.style === null) {
      menu.removeAttribute("style");
    } else {
      menu.setAttribute("style", portalled.style);
    }
    portalled.placeholder.replaceWith(menu);
    portalled = null;
  }

  function openPortal(dropdown) {
    var menu = dropdown.querySelector(".rv-dropdown__menu");
    var trigger = dropdown.querySelector("[data-rv-dropdown]");
    if (!menu || !trigger || (portalled && portalled.menu === menu)) return;

    closePortal();

    var placeholder = document.createComment("rv-dropdown");
    portalled = { menu: menu, placeholder: placeholder, style: menu.getAttribute("style") };

    menu.replaceWith(placeholder);
    // The template's inline left/right would fight the fixed coordinates.
    menu.removeAttribute("style");
    menu.classList.add("rv-dropdown__menu--portal");
    document.body.appendChild(menu);

    var anchor = trigger.getBoundingClientRect();
    var box = menu.getBoundingClientRect();
    var alignLeft = menu.hasAttribute("data-rv-align-left") || dropdown.hasAttribute("data-rv-align-left");

    var left = alignLeft ? anchor.left : anchor.right - box.width;
    left = Math.max(8, Math.min(left, window.innerWidth - box.width - 8));

    var top = anchor.bottom + 4;
    if (top + box.height > window.innerHeight - 8) {
      var above = anchor.top - box.height - 4;
      top = above >= 8 ? above : Math.max(8, window.innerHeight - box.height - 8);
    }

    menu.style.left = Math.round(left) + "px";
    menu.style.top = Math.round(top) + "px";
  }

  function initDropdownPortals() {
    // Watching the class is deterministic; hooking the click was order-dependent.
    var observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        var dropdown = record.target;
        if (!dropdown.classList || !dropdown.classList.contains("rv-dropdown")) return;
        if (dropdown.classList.contains("is-open")) {
          openPortal(dropdown);
        } else if (portalled && dropdown.contains(portalled.placeholder)) {
          closePortal();
        }
      });
    });
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });

    // A scroll inside the menu is the user reading it, not leaving it.
    window.addEventListener("scroll", function (event) {
      if (!portalled) return;
      if (event.target && event.target.closest && event.target.closest(".rv-dropdown__menu")) return;
      $(".rv-dropdown").removeClass("is-open");
      closePortal();
    }, true);
    window.addEventListener("resize", function () {
      if (!portalled) return;
      $(".rv-dropdown").removeClass("is-open");
      closePortal();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closePortal();
    });

    // A portalled menu lives outside the swap target, so retire it around the
    // request. A request that came FROM the menu must keep it until it settles,
    // or the form is detached mid-flight and the swap never lands.
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var source = event.detail && event.detail.elt;
      if (portalled && source && portalled.menu.contains(source)) return;
      closePortal();
    });
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var source = event.detail && event.detail.elt;
      if (portalled && source && portalled.menu.contains(source)) return;
      closePortal();
    });
    document.body.addEventListener("htmx:afterRequest", function () {
      $(".rv-dropdown").removeClass("is-open");
      closePortal();
    });
  }

  /* ------------------------------------------------------ spinners */
  function markLoading(button) {
    if (!button || button.classList.contains("is-loading")) return;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    if (button.tagName === "BUTTON") button.disabled = true;
  }

  function initSpinners() {
    // Any form submit spins its own submit control.
    $(document).on("submit", "form", function () {
      var submit = this.querySelector('button[type="submit"], input[type="submit"]');
      if (submit) markLoading(submit);
    });

    // Links that navigate away, excluding HTMX swaps and new tabs.
    $(document).on("click", "a.rv-btn[href]", function (event) {
      if (
        event.metaKey || event.ctrlKey || event.shiftKey ||
        this.target === "_blank" ||
        this.hasAttribute("hx-get") ||
        this.getAttribute("href").charAt(0) === "#"
      ) {
        return;
      }
      markLoading(this);
    });

    // A cached back-navigation must not leave a button stuck spinning.
    window.addEventListener("pageshow", function () {
      $(".rv-btn.is-loading").removeClass("is-loading").removeAttr("aria-busy").prop("disabled", false);
    });
  }

  /* -------------------------------------------- permission toggles */
  function initPermissionToggles() {
    $(document).on("change", "[data-rv-permission]", function () {
      var input = this;
      var label = input.closest(".rv-switch");
      var allowed = input.checked;
      label.classList.add("is-saving");

      var body = new URLSearchParams();
      body.set("page_key", input.dataset.page);
      body.set("allowed", allowed ? "true" : "false");

      fetch(input.dataset.url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: body.toString(),
        credentials: "same-origin",
      })
        .then(function (response) {
          if (!response.ok) throw new Error(String(response.status));
          return response.json();
        })
        .then(function () {
          label.classList.remove("is-saving");
          if (window.RV && RV.toast) RV.toast("Permission updated.", "success");
        })
        .catch(function () {
          // Never leave the switch showing a state the server did not accept.
          input.checked = !allowed;
          label.classList.remove("is-saving");
          if (window.RV && RV.toast) RV.toast("Could not save that permission.", "error");
        });
    });
  }

  function csrfToken() {
    var field = document.querySelector("[name=csrfmiddlewaretoken]");
    if (field) return field.value;
    var match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[2]) : "";
  }

  RV.markLoading = markLoading;

  $(function () {
    initTheme();
    initClock();
    initDropdownPortals();
    initSpinners();
    initPermissionToggles();
  });
})(window.jQuery);
