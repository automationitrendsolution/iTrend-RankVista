/* Live form validation. The server runs the same Django form, so no rule is
   duplicated here and uniqueness checks work as you type. */
(function ($) {
  "use strict";

  var DEBOUNCE_MS = 400;

  function csrfToken(form) {
    var field = form.querySelector("[name=csrfmiddlewaretoken]");
    if (field) return field.value;
    var match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[2]) : "";
  }

  function fieldWrapper(form, name) {
    var input = form.querySelector("[name='" + name + "']");
    return input ? input.closest(".rv-field") : null;
  }

  function paint(form, payload, touched) {
    Object.keys(form._rvFields || {}).forEach(function (name) {
      var wrap = fieldWrapper(form, name);
      if (!wrap || !touched.has(name)) return;

      var message = payload.errors[name];
      var slot = wrap.querySelector(".rv-field__error");
      if (message) {
        if (!slot) {
          slot = document.createElement("div");
          slot.className = "rv-field__error";
          wrap.appendChild(slot);
        }
        slot.textContent = message;
        wrap.classList.add("is-invalid");
        wrap.classList.remove("is-valid");
      } else {
        if (slot) slot.remove();
        wrap.classList.remove("is-invalid");
        wrap.classList.toggle("is-valid", payload.valid.indexOf(name) !== -1);
      }
    });

    var submit = form.querySelector('button[type="submit"]');
    if (submit) submit.classList.toggle("is-blocked", Object.keys(payload.errors).length > 0);
  }

  function validate(form) {
    var touched = form._rvTouched;
    if (!touched || touched.size === 0) return;

    var data = new FormData(form);
    data.set("_touched", Array.from(touched).join(","));

    fetch(form.dataset.rvValidate, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(form), "X-Requested-With": "XMLHttpRequest" },
      body: data,
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      })
      .then(function (payload) {
        paint(form, payload, touched);
      })
      .catch(function () {
        // Validation is an aid; a failure must never block the real submit.
      });
  }

  function attach(form) {
    if (form._rvValidateBound) return;
    form._rvValidateBound = true;
    form._rvTouched = new Set();
    form._rvFields = {};

    form.querySelectorAll("[name]").forEach(function (input) {
      if (input.name.charAt(0) === "_" || input.name === "csrfmiddlewaretoken") return;
      form._rvFields[input.name] = true;
    });

    var timer = null;
    function schedule(name, immediate) {
      form._rvTouched.add(name);
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { validate(form); }, immediate ? 0 : DEBOUNCE_MS);
    }

    $(form).on("input", "input, textarea", function () {
      if (this.name && form._rvFields[this.name]) schedule(this.name, false);
    });
    // Leaving a field, or picking from a select, should report at once.
    $(form).on("blur", "input, textarea", function () {
      if (this.name && form._rvFields[this.name]) schedule(this.name, true);
    }, true);
    $(form).on("change", "select, input[type=checkbox]", function () {
      if (this.name && form._rvFields[this.name]) schedule(this.name, true);
    });
  }

  function scan(scope) {
    (scope || document).querySelectorAll("form[data-rv-validate]").forEach(attach);
  }

  $(function () {
    scan();
    document.body.addEventListener("htmx:afterSwap", function (event) {
      scan(event.detail && event.detail.target);
      scan(document.getElementById("rv-modal-root"));
    });
  });

  window.RV = window.RV || {};
  window.RV.scanValidation = scan;
})(window.jQuery);
