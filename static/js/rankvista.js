/* iTrend RankVista shell behaviour: navigation, dropdowns, modals, toasts, tables. */
(function ($) {
  "use strict";

  var RV = (window.RV = window.RV || {});
  var STORAGE_KEY = "rv.sidebar.collapsed";

  /* ---------------------------------------------------------- sidebar */
  function initSidebar() {
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === "1") {
        document.body.classList.add("rv-collapsed");
      }
    } catch (e) {
      /* private mode: collapse state simply does not persist */
    }

    $(document).on("click", "[data-rv-toggle-sidebar]", function () {
      var collapsed = document.body.classList.toggle("rv-collapsed");
      try {
        window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
      } catch (e) {
        /* ignore */
      }
    });

    $(document).on("click", "[data-rv-toggle-nav]", function () {
      document.body.classList.toggle("rv-nav-open");
    });

    $(document).on("click", function (event) {
      if (
        document.body.classList.contains("rv-nav-open") &&
        !$(event.target).closest(".rv-sidebar, [data-rv-toggle-nav]").length
      ) {
        document.body.classList.remove("rv-nav-open");
      }
    });
  }

  /* --------------------------------------------------------- dropdowns */
  function initDropdowns() {
    $(document).on("click", "[data-rv-dropdown]", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var parent = $(this).closest(".rv-dropdown");
      var wasOpen = parent.hasClass("is-open");
      $(".rv-dropdown").removeClass("is-open");
      parent.toggleClass("is-open", !wasOpen);
      $(this).attr("aria-expanded", String(!wasOpen));
    });

    $(document).on("click", function (event) {
      if (!$(event.target).closest(".rv-dropdown").length) {
        $(".rv-dropdown").removeClass("is-open");
        $("[data-rv-dropdown]").attr("aria-expanded", "false");
      }
    });

    $(document).on("keydown", function (event) {
      if (event.key === "Escape") {
        $(".rv-dropdown").removeClass("is-open");
      }
    });
  }

  /* ------------------------------------------------------------- modal */
  RV.closeModal = function () {
    $("#rv-modal-root").empty();
    $(document.body).css("overflow", "");
  };

  function initModals() {
    $(document).on("click", "[data-rv-close-modal]", function (event) {
      event.preventDefault();
      RV.closeModal();
    });

    $(document).on("click", ".rv-modal-backdrop", function (event) {
      if (event.target === this) {
        RV.closeModal();
      }
    });

    $(document).on("keydown", function (event) {
      if (event.key === "Escape" && $("#rv-modal-root").children().length) {
        RV.closeModal();
      }
    });

    // Trap focus inside an open modal so keyboard users cannot tab behind it.
    $(document).on("keydown", ".rv-modal", function (event) {
      if (event.key !== "Tab") return;
      var focusable = $(this)
        .find("a[href], button:not([disabled]), input:not([disabled]), select, textarea")
        .filter(":visible");
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  /* ------------------------------------------------------------ toasts */
  RV.toast = function (message, variant) {
    var root = $("#rv-toasts");
    if (!root.length) {
      root = $('<div class="rv-toasts" id="rv-toasts" role="status" aria-live="polite"></div>').appendTo(
        document.body
      );
    }
    var toast = $('<div class="rv-toast"></div>')
      .addClass("rv-toast--" + (variant || "info"))
      .append($("<div></div>").text(message))
      .append('<button type="button" class="rv-toast__close" aria-label="Dismiss">&times;</button>');
    root.append(toast);
    window.setTimeout(function () {
      toast.fadeOut(180, function () {
        toast.remove();
      });
    }, 5000);
  };

  function initToasts() {
    $(document).on("click", ".rv-toast__close", function () {
      $(this).closest(".rv-toast").remove();
    });
    window.setTimeout(function () {
      $(".rv-toast[data-rv-autohide]").fadeOut(200, function () {
        $(this).remove();
      });
    }, 5000);
  }

  /* --------------------------------------------------------- password */
  function initPasswordToggles() {
    $(document).on("click", "[data-rv-password-toggle]", function () {
      var button = $(this);
      var input = button.closest(".rv-password").find("input");
      var showing = input.attr("type") === "text";
      input.attr("type", showing ? "password" : "text");
      button.attr("aria-label", showing ? "Show password" : "Hide password");
      button.find("[data-eye-open]").toggle(showing);
      button.find("[data-eye-closed]").toggle(!showing);
    });
  }

  /* ----------------------------------------------------- form loading */
  function initFormStates() {
    $(document).on("submit", "form[data-rv-loading]", function () {
      $(this).find('button[type="submit"]').addClass("is-loading").prop("disabled", true);
    });
  }

  /* ------------------------------------------------- table selection */
  function initTableSelection() {
    $(document).on("change", "[data-rv-select-all]", function () {
      var checked = this.checked;
      var scope = $(this).closest("table");
      scope.find("[data-rv-select-row]").prop("checked", checked);
      updateSelectionCount(scope);
    });

    $(document).on("change", "[data-rv-select-row]", function () {
      var scope = $(this).closest("table");
      var rows = scope.find("[data-rv-select-row]");
      var selected = rows.filter(":checked");
      scope
        .find("[data-rv-select-all]")
        .prop("checked", rows.length === selected.length && rows.length > 0)
        .prop("indeterminate", selected.length > 0 && selected.length < rows.length);
      updateSelectionCount(scope);
    });
  }

  function updateSelectionCount(scope) {
    var count = scope.find("[data-rv-select-row]:checked").length;
    $("[data-rv-selection-count]").text(count).closest("[data-rv-selection-bar]").toggle(count > 0);
  }

  /* ----------------------------------------------- sticky matrix sync */
  function initMatrixScroll() {
    // Keep the horizontal position when HTMX swaps the matrix body back in.
    var scroller = document.querySelector("[data-rv-matrix-scroll]");
    if (!scroller) return;
    var stored = window.sessionStorage
      ? window.sessionStorage.getItem("rv.matrix.scroll")
      : null;
    if (stored) {
      scroller.scrollLeft = parseInt(stored, 10) || 0;
    }
    $(scroller).on("scroll", function () {
      try {
        window.sessionStorage.setItem("rv.matrix.scroll", String(scroller.scrollLeft));
      } catch (e) {
        /* ignore */
      }
    });
  }

  /* ------------------------------------------------------------ HTMX */
  function initHtmx() {
    document.body.addEventListener("htmx:afterSwap", function () {
      initMatrixScroll();
      $(".rv-dropdown").removeClass("is-open");
    });

    document.body.addEventListener("htmx:responseError", function (event) {
      var status = event.detail && event.detail.xhr ? event.detail.xhr.status : 0;
      RV.toast(
        status === 403
          ? "You do not have permission to do that."
          : "Something went wrong loading that view. Please retry.",
        "error"
      );
    });

    document.body.addEventListener("htmx:sendError", function () {
      RV.toast("Network error. Check your connection and retry.", "error");
    });
  }

  /* -------------------------------------------------- clickable rows */
  function initRowLinks() {
    $(document).on("click", ".rv-row-link", function (event) {
      if ($(event.target).closest("a, button, input, .rv-dropdown").length) return;
      var href = this.getAttribute("data-href");
      if (href) window.location.href = href;
    });
  }

  /* ------------------------------------------------------------- init */
  $(function () {
    initSidebar();
    initDropdowns();
    initModals();
    initToasts();
    initPasswordToggles();
    initFormStates();
    initTableSelection();
    initMatrixScroll();
    initRowLinks();
    initHtmx();
  });
})(window.jQuery);
