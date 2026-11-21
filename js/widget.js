/* 锁屏壁纸预览 — 橹穆, no localStorage */
(function () {
  "use strict";

  const PHOTOS = ["01", "03", "05", "06", "07", "08", "09", "11", "12", "13", "14"];
  const LINE = "穆之所及，杰是美好。";

  const $ = (id) => document.getElementById(id);
  let DATA = null;
  let photoIndex = 0;
  let toolbarOn = true;

  function todayISO() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
  }
  function rec(iso) { return DATA && DATA.days ? DATA.days[iso] : null; }

  function statusText(d) {
    if (!d) return "";
    if (d.holiday) {
      const short = d.holiday.short || d.holiday.name || "";
      const type = d.holiday.type;
      if (type === "班") return short ? "班 · " + short : "调班上班";
      return (type || "休") + (short ? " · " + short : "");
    }
    if (d.kind === "周末") return "周末";
    return "";
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function formatLine(text) {
    const s = text || "";
    if (!s.includes("，")) return escapeHtml(s);
    const i = s.indexOf("，");
    return escapeHtml(s.slice(0, i + 1)) + "<br>" + escapeHtml(s.slice(i + 1));
  }

  function applyPhoto() {
    $("bg").src = "./icons/widget-" + PHOTOS[photoIndex] + ".webp";
  }
  function applyQuote() {
    $("lyric-line").innerHTML = formatLine(LINE);
  }
  function nextPhoto() {
    photoIndex = (photoIndex + 1) % PHOTOS.length;
    applyPhoto();
  }
  function applyToday() {
    const iso = todayISO();
    const [, m, d] = iso.split("-").map(Number);
    $("date").textContent = m + "月" + d + "日";
    const recd = rec(iso);
    const week = recd && recd.weekdayName ? recd.weekdayName : weekdayName(iso);
    $("week").textContent = week;
    const lunarBits = recd
      ? [recd.lunarText ? "农历" + recd.lunarText : "", recd.solarTerm, recd.traditionalFestival, recd.gregorianFestival].filter(Boolean)
      : [];
    $("lunar").textContent = lunarBits.join(" · ");
    const st = statusText(recd);
    const el = $("status");
    if (st) {
      el.hidden = false;
      el.textContent = st;
      el.classList.toggle("is-off", !(recd && recd.holiday && recd.holiday.type === "班"));
    } else {
      el.hidden = true;
    }
  }
  function weekdayName(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return "星期" + "日一二三四五六"[new Date(y, m - 1, d).getDay()];
  }

  function setToolbar(on) {
    toolbarOn = on;
    $("toolbar").classList.toggle("is-off", !on);
    document.querySelector(".content").classList.toggle("with-bar", on);
  }

  function bind() {
    document.getElementById("stage").addEventListener("click", (e) => {
      if (e.target.closest(".toolbar") || e.target.closest(".lyric-card")) return;
      setToolbar(!toolbarOn);
    });
    $("btn-photo").addEventListener("click", (e) => { e.stopPropagation(); nextPhoto(); });
  }

  function applyQuery() {
    const q = new URLSearchParams(location.search);
    const photo = q.get("photo");
    if (photo && PHOTOS.includes(photo)) photoIndex = PHOTOS.indexOf(photo);
    if (q.get("ui") === "0" || q.get("chrome") === "0") setToolbar(false);
  }

  async function boot() {
    bind();
    applyQuery();
    applyPhoto();
    applyQuote();
    try {
      const res = await fetch("./data/calendar-data.json", { cache: "reload" });
      DATA = await res.json();
    } catch (e) {
      DATA = { quotes: [], days: {} };
    }
    applyToday();
    applyQuote();
  }
  boot();
})();
