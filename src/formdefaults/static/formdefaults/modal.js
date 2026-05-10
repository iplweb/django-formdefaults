(function () {
  "use strict";

  function findHost(button) {
    var sibling = button.parentElement && button.parentElement.querySelector(".fd-modal-host");
    return sibling || document.querySelector(".fd-modal-host");
  }

  function open(host, html) {
    host.innerHTML = html;
    host.hidden = false;
  }

  function close(host) {
    host.innerHTML = "";
    host.hidden = true;
  }

  function csrfFromCookie() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  document.addEventListener("click", async function (e) {
    var btn = e.target.closest && e.target.closest(".fd-edit-btn");
    if (btn) {
      var url = btn.dataset.fdUrl;
      var host = findHost(btn);
      if (!host) return;
      host.dataset.fdUrl = url;
      var resp = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      open(host, await resp.text());
      return;
    }
    var closeEl = e.target.closest && e.target.closest(".fd-modal-close");
    if (closeEl) {
      var host2 = closeEl.closest(".fd-modal-host");
      if (host2) close(host2);
      return;
    }
    if (e.target.classList && e.target.classList.contains("fd-modal-backdrop")) {
      var host3 = e.target.closest(".fd-modal-host");
      if (host3) close(host3);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".fd-modal-host:not([hidden])").forEach(close);
    }
  });

  document.addEventListener("submit", async function (e) {
    var form = e.target.closest && e.target.closest("[data-fd-form]");
    if (!form) return;
    e.preventDefault();
    var host = form.closest(".fd-modal-host");
    if (!host) return;
    var url = host.dataset.fdUrl;
    var fd = new FormData(form);
    var resp = await fetch(url, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfFromCookie() },
    });
    host.innerHTML = await resp.text();
  });
})();
