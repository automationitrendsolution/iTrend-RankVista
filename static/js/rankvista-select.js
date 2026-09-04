/* Custom select. The native <select> stays in the DOM and remains the source of
   truth, so form submission, HTMX triggers and validation are unchanged. */
(function ($) {
  "use strict";

  var SELECTOR = "select.rv-select:not([multiple]):not([data-rv-native])";
  var counter = 0;

  function build(select) {
    if (select.dataset.rvEnhanced) return;
    // A re-executed script could otherwise wrap the same select twice.
    if (select.closest(".rv-select-wrap")) {
      select.dataset.rvEnhanced = "1";
      return;
    }
    select.dataset.rvEnhanced = "1";

    var id = "rv-select-" + ++counter;
    var wrap = document.createElement("div");
    wrap.className = "rv-select-wrap";
    if (select.style.width) wrap.style.width = select.style.width;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "rv-select-btn";
    button.id = id + "-btn";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    var label = select.getAttribute("aria-label");
    if (label) button.setAttribute("aria-label", label);

    var text = document.createElement("span");
    text.className = "rv-select-btn__text";
    button.appendChild(text);

    var caret = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    caret.setAttribute("class", "rv-select-btn__caret");
    caret.setAttribute("aria-hidden", "true");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#rv-i-chevron-down");
    caret.appendChild(use);
    button.appendChild(caret);

    var menu = document.createElement("div");
    menu.className = "rv-select-menu";
    menu.setAttribute("role", "listbox");
    menu.id = id + "-menu";
    menu._rvWrap = wrap;

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    wrap.appendChild(button);
    wrap.appendChild(menu);
    select.classList.add("rv-select--hidden");

    function renderOptions() {
      menu.innerHTML = "";
      Array.prototype.forEach.call(select.options, function (option, index) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "rv-select-option";
        item.setAttribute("role", "option");
        item.dataset.index = index;
        item.textContent = option.textContent;
        if (option.disabled) item.disabled = true;
        if (option.selected) {
          item.classList.add("is-selected");
          item.setAttribute("aria-selected", "true");
        }
        menu.appendChild(item);
      });
    }

    function syncLabel() {
      var option = select.options[select.selectedIndex];
      text.textContent = option ? option.textContent : "";
      button.disabled = select.disabled;
    }

    function close() {
      wrap.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      // The portal class forces display:block and position:fixed, so it must go
      // or the menu stays visible after being moved back into the wrap.
      menu.classList.remove("rv-select-menu--portal");
      menu.removeAttribute("style");
      if (menu.parentElement !== wrap) wrap.appendChild(menu);
    }

    function position() {
      // Rendered on <body> so a scroll container can never clip it.
      document.body.appendChild(menu);
      menu.classList.add("rv-select-menu--portal");

      var anchor = button.getBoundingClientRect();
      menu.style.minWidth = Math.round(anchor.width) + "px";
      var box = menu.getBoundingClientRect();

      var left = Math.max(8, Math.min(anchor.left, window.innerWidth - box.width - 8));
      var top = anchor.bottom + 4;
      if (top + box.height > window.innerHeight - 8) {
        var above = anchor.top - box.height - 4;
        top = above >= 8 ? above : Math.max(8, window.innerHeight - box.height - 8);
      }
      menu.style.left = Math.round(left) + "px";
      menu.style.top = Math.round(top) + "px";
    }

    function open() {
      if (select.disabled) return;
      closeAll();
      renderOptions();
      wrap.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
      position();
      var selected = menu.querySelector(".is-selected") || menu.firstElementChild;
      if (selected) selected.focus();
    }

    function choose(index) {
      if (select.selectedIndex !== index) {
        select.selectedIndex = index;
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      syncLabel();
      close();
      button.focus();
    }

    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      wrap.classList.contains("is-open") ? close() : open();
    });

    menu.addEventListener("click", function (event) {
      var option = event.target.closest(".rv-select-option");
      if (option && !option.disabled) choose(parseInt(option.dataset.index, 10));
    });

    menu.addEventListener("keydown", function (event) {
      var items = [].slice.call(menu.querySelectorAll(".rv-select-option:not([disabled])"));
      var at = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        var next = event.key === "ArrowDown" ? at + 1 : at - 1;
        if (next < 0) next = items.length - 1;
        if (next >= items.length) next = 0;
        items[next].focus();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (document.activeElement.classList.contains("rv-select-option")) {
          choose(parseInt(document.activeElement.dataset.index, 10));
        }
      } else if (event.key === "Escape" || event.key === "Tab") {
        close();
        button.focus();
      }
    });

    button.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });

    // Anything that changes the select programmatically refreshes the label.
    select.addEventListener("change", syncLabel);
    wrap._rvClose = close;
    syncLabel();
  }

  function closeAll(except) {
    // Close by menu, not by wrap: a stuck menu may have lost the is-open class.
    document.querySelectorAll(".rv-select-wrap").forEach(function (wrap) {
      if (wrap !== except && wrap._rvClose) wrap._rvClose();
    });
    // A swap can destroy a wrap while its menu still sits on <body>. Remove only
    // those orphans; a menu whose wrap is still connected must survive.
    document.body.querySelectorAll(":scope > .rv-select-menu--portal").forEach(function (menu) {
      if (!menu._rvWrap || !menu._rvWrap.isConnected) menu.remove();
    });
  }

  function enhance(scope) {
    (scope || document).querySelectorAll(SELECTOR).forEach(build);
  }

  $(function () {
    enhance();

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".rv-select-wrap, .rv-select-menu")) closeAll();
    });
    // Reposition or close on page scroll, but never when the scroll happened
    // inside the open menu itself.
    window.addEventListener("scroll", function (event) {
      if (event.target && event.target.closest && event.target.closest(".rv-select-menu")) return;
      closeAll();
    }, true);
    window.addEventListener("resize", function () { closeAll(); });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      closeAll();
      enhance(event.detail && event.detail.target);
    });
    document.body.addEventListener("htmx:beforeSwap", function () { closeAll(); });
  });

  window.RV = window.RV || {};
  window.RV.enhanceSelects = enhance;
})(window.jQuery);
