/* iTrend RankVista shell behaviour: navigation, dropdowns, modals, toasts, tables. */
(function ($) {
  "use strict";

  var RV = (window.RV = window.RV || {});
  var STORAGE_KEY = "rv.sidebar.collapsed";
  var TOAST_TIMEOUT = 3000;

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
    }, TOAST_TIMEOUT);
  };

  function initToasts() {
    $(document).on("click", ".rv-toast__close", function () {
      $(this).closest(".rv-toast").remove();
    });
    window.setTimeout(function () {
      $(".rv-toast[data-rv-autohide]").fadeOut(200, function () {
        $(this).remove();
      });
    }, TOAST_TIMEOUT);
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
      var table = $(this).closest("table");
      // Inside a table select that table; on the toolbar select everything shown.
      var rows = table.length ? table.find("[data-rv-select-row]") : $("[data-rv-select-row]");
      rows.prop("checked", checked);
      updateSelectionCount();
    });

    $(document).on("change", "[data-rv-select-row]", updateSelectionCount);

    // Copy the current selection into the bulk form just before it submits.
    $(document).on("submit", "form[data-rv-selection-form]", function () {
      var form = this;
      $(form).find('input[name="project_ids"]').remove();
      $("[data-rv-select-row]:checked").each(function () {
        $("<input>", { type: "hidden", name: "project_ids", value: this.value }).appendTo(form);
      });
    });

    $(document).on("click", "[data-rv-selection-clear]", function () {
      $("[data-rv-select-row], [data-rv-select-all]").prop("checked", false).prop("indeterminate", false);
      updateSelectionCount();
    });

    // A card checkbox must not also open the project.
    $(document).on("click", ".rv-project-card__select", function (event) {
      event.stopPropagation();
    });

    document.body.addEventListener("htmx:afterSwap", updateSelectionCount);
  }

  function updateSelectionCount() {
    // Cards are not inside a table, so counting is always document-wide.
    var rows = $("[data-rv-select-row]");
    var count = rows.filter(":checked").length;
    $("[data-rv-selection-count]").text(count);
    $("[data-rv-selection-bar]").prop("hidden", count === 0);
    $("[data-rv-select-all]")
      .prop("checked", rows.length > 0 && count === rows.length)
      .prop("indeterminate", count > 0 && count < rows.length);
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

  /* ----------------------------------------------------- confirm */
  RV.confirm = function (options) {
    return new Promise(function (resolve) {
      var template = document.getElementById("rv-confirm-template");
      if (!template) {
        // Without the template there is nothing to show; refuse rather than
        // silently performing a destructive action.
        resolve(false);
        return;
      }

      var node = template.content.firstElementChild.cloneNode(true);
      node.querySelector("[data-rv-confirm-title]").textContent = options.title || "Are you sure?";
      node.querySelector("[data-rv-confirm-body]").textContent = options.message || "";

      var accept = node.querySelector("[data-rv-confirm-accept]");
      accept.textContent = options.confirmLabel || "Confirm";
      if (options.danger) {
        accept.classList.remove("rv-btn--primary");
        accept.classList.add("rv-btn--danger-solid");
        node.querySelector("[data-rv-confirm-icon]").classList.add("is-danger");
      }

      function settle(result) {
        node.remove();
        $(document).off("keydown.rvconfirm");
        resolve(result);
      }

      accept.addEventListener("click", function () { settle(true); });
      node.querySelector("[data-rv-confirm-cancel]").addEventListener("click", function () { settle(false); });
      node.addEventListener("click", function (event) { if (event.target === node) settle(false); });
      $(document).on("keydown.rvconfirm", function (event) {
        if (event.key === "Escape") settle(false);
      });

      document.body.appendChild(node);
      accept.focus();
    });
  };

  function initConfirm() {
    $(document).on("submit", "form[data-rv-confirm]", function (event) {
      var form = this;
      if (form.dataset.rvConfirmed === "1") {
        delete form.dataset.rvConfirmed;
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();

      RV.confirm({
        title: form.dataset.rvConfirmTitle || "Please confirm",
        message: form.dataset.rvConfirm,
        confirmLabel: form.dataset.rvConfirmLabel || "Confirm",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        form.dataset.rvConfirmed = "1";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
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
    initConfirm();
    initHtmx();
  });
})(window.jQuery);
