/* eSIMsterr — one small vanilla script. No framework, no build step. */
(function () {
  "use strict";

  /* ---------- theme ------------------------------------------------------ */
  var root = document.documentElement;
  function setTheme(t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("esimsterr-theme", t); } catch (e) {}
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-theme-toggle]");
    if (!t) return;
    setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });

  /* ---------- sticky nav shadow ------------------------------------------ */
  var navWrap = document.querySelector(".nav-wrap");
  if (navWrap) {
    var onScroll = function () { navWrap.classList.toggle("is-scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ---------- dropdown menus --------------------------------------------- */
  function closeMenus(except) {
    document.querySelectorAll("[data-menu]").forEach(function (m) {
      if (m === except) return;
      m.hidden = true;
      var btn = document.querySelector('[data-menu-btn="' + m.dataset.menu + '"]');
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-menu-btn]");
    if (btn) {
      var menu = document.querySelector('[data-menu="' + btn.dataset.menuBtn + '"]');
      if (menu) {
        var open = menu.hidden;
        closeMenus(open ? menu : null);
        menu.hidden = !open;
        btn.setAttribute("aria-expanded", String(open));
      }
      return;
    }
    if (!e.target.closest("[data-menu]")) closeMenus(null);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenus(null); });

  /* ---------- mobile panel ----------------------------------------------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-mobile-toggle]");
    if (!t) return;
    var panel = document.getElementById("mobile-panel");
    if (!panel) return;
    panel.hidden = !panel.hidden;
    document.body.style.overflow = panel.hidden ? "" : "hidden";
  });

  /* ---------- destination search typeahead -------------------------------- */
  var search = document.querySelector("[data-search]");
  if (search) {
    var input = search.querySelector("input");
    var box = search.parentElement.querySelector("[data-search-results]");
    var timer = null, activeIndex = -1, items = [];

    function render(results, q) {
      if (!results.length) {
        box.innerHTML = '<div class="search-empty">No destination matches “' +
          escapeHtml(q) + '”. Try a country name.</div>';
        box.hidden = false;
        items = [];
        return;
      }
      box.innerHTML = results.map(function (r, i) {
        var price = r.from ? '<span class="price">from $' + r.from + "</span>" : "";
        var note = r.note ? '<span class="note">' + escapeHtml(r.note) + "</span>" : "";
        return '<a class="search-result" data-i="' + i + '" href="' + r.url + '">' +
          '<span class="flag">' + r.flag + "</span>" +
          '<span><span class="name">' + escapeHtml(r.name) + "</span>" + note + "</span>" +
          price + "</a>";
      }).join("");
      box.hidden = false;
      items = Array.prototype.slice.call(box.querySelectorAll(".search-result"));
      activeIndex = -1;
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    }

    function query() {
      var q = input.value.trim();
      if (!q) { box.hidden = true; return; }
      fetch("/api/search/?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (d) { render(d.results || [], q); })
        .catch(function () { box.hidden = true; });
    }

    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(query, 160);
    });
    input.addEventListener("focus", function () { if (input.value.trim()) query(); });
    input.addEventListener("keydown", function (e) {
      if (box.hidden || !items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        items.forEach(function (el) { el.classList.remove("is-active"); });
        activeIndex += e.key === "ArrowDown" ? 1 : -1;
        if (activeIndex < 0) activeIndex = items.length - 1;
        if (activeIndex >= items.length) activeIndex = 0;
        items[activeIndex].classList.add("is-active");
        items[activeIndex].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        window.location.href = items[activeIndex].getAttribute("href");
      }
    });
    document.addEventListener("click", function (e) {
      if (!search.contains(e.target) && !box.contains(e.target)) box.hidden = true;
    });
  }

  /* ---------- tabs (plan groups, dashboards) ------------------------------ */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-tab]");
    if (!btn) return;
    var group = btn.closest("[data-tabs]");
    if (!group) return;
    group.querySelectorAll("[data-tab]").forEach(function (b) {
      b.setAttribute("aria-selected", String(b === btn));
    });
    var scope = document.querySelector(group.dataset.tabs) || document;
    scope.querySelectorAll("[data-tab-panel]").forEach(function (p) {
      p.hidden = p.dataset.tabPanel !== btn.dataset.tab;
    });
  });

  /* ---------- copy to clipboard ------------------------------------------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var text = btn.dataset.copy;
    var done = function () {
      var old = btn.dataset.label || btn.textContent;
      btn.dataset.label = old;
      btn.textContent = "Copied";
      setTimeout(function () { btn.textContent = old; }, 1600);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done).catch(done);
    else {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (err) {}
      document.body.removeChild(ta); done();
    }
  });

  /* ---------- reveal on scroll -------------------------------------------- */
  var revealables = document.querySelectorAll(".reveal");
  if (revealables.length && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { entry.target.classList.add("in"); io.unobserve(entry.target); }
      });
    }, { rootMargin: "0px 0px -40px 0px", threshold: 0.05 });
    revealables.forEach(function (el) { io.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------- order status polling ---------------------------------------- */
  var poller = document.querySelector("[data-poll-url]");
  if (poller) {
    var tries = 0;
    var tick = function () {
      tries++;
      fetch(poller.dataset.pollUrl)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.reload) { window.location.reload(); return; }
          if (tries < 40) setTimeout(tick, tries < 10 ? 2000 : 5000);
        })
        .catch(function () { if (tries < 40) setTimeout(tick, 5000); });
    };
    setTimeout(tick, 2500);
  }

  /* ---------- submit button loading state --------------------------------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches("form")) return;
    var btn = form.querySelector('[type="submit"]');
    if (btn && !btn.disabled) {
      btn.classList.add("is-loading");
      var text = btn.textContent;
      btn.innerHTML = '<span class="spinner"></span> ' + text;
    }
  });

  /* ---------- Google Identity Services ------------------------------------ */
  window.esimsterrGoogle = function (response) {
    var form = document.getElementById("google-form");
    if (!form) return;
    form.querySelector('[name="credential"]').value = response.credential;
    form.submit();
  };
})();
