/* 锁屏壁纸预览 — 橹穆, no localStorage */
(function () {
  "use strict";

  const PHOTOS = ["01", "03", "05", "06", "07", "08", "09", "11", "12", "13", "14"];
  const FALLBACK_QUOTES = [
    { text: "🩵🩷橹穆星途璀璨。", from: "" },
    { text: "十指紧相扣，橹穆常相见。", from: "" },
    { text: "🩵🩷幸福降临橹穆手心。", from: "" },
    { text: "🩵🩷世界纷纷扰扰，橹穆白头偕老。", from: "" },
    { text: "🩵🩷穆之所及，杰是美好。", from: "" },
    { text: "🩵🩷橹是木制成的，杰是木止沉的。", from: "" },
    { text: "🩵🩷橹橹春韵，穆穆良朝。", from: "" },
    { text: "爱能克服远距离，多远都要在一起。", from: "" },
    { text: "橹穆的世杰祉有彼此。", from: "" },
    { text: "紧张吗有点，看球吗不看。", from: "" }
  ];

  const $ = (id) => document.getElementById(id);
  let DATA = null;
  let quotes = FALLBACK_QUOTES.slice();
  let photoIndex = 0;
  let quoteIndex = 0;
  let toolbarOn = true;
  const QUOTE_INTERVAL_MS = 10000;
  let quoteTimer = null;

  function todayISO() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
  }
  function rec(iso) { return DATA && DATA.days ? DATA.days[iso] : null; }

  function statusText(d) {
    if (!d) return "";
    if (d.holiday) {
      const short = d.holiday.short || d.holiday.name || "";
      const type = d.holiday.type;
      if (type === "班") return short ? "班 · " + short : "调休上班";
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
  /* Break at the most balanced comma so long quotes do not overflow a phone width. */
  function formatLine(text) {
    const s = text || "";
    const n = [...s].length;
    if (n <= 12 || !s.includes("，")) return escapeHtml(s);
    let bestAt = -1, bestScore = Infinity;
    for (let i = 0; i < s.length; i++) {
      if (s[i] !== "，") continue;
      const left = [...s.slice(0, i + 1)].length;
      const score = Math.abs(left - (n - left));
      if (score < bestScore) { bestScore = score; bestAt = i; }
    }
    if (bestAt < 0) return escapeHtml(s);
    return escapeHtml(s.slice(0, bestAt + 1)) + "<br>" + escapeHtml(s.slice(bestAt + 1));
  }

  function applyPhoto() {
    $("bg").src = "./icons/widget-" + PHOTOS[photoIndex] + ".webp";
  }
  function applyQuote() {
    if (!quotes.length) {
      $("lyric-line").textContent = "";
      return;
    }
    const q = quotes[quoteIndex % quotes.length];
    $("lyric-line").innerHTML = formatLine(q.text || "");
  }
  function nextPhoto() {
    photoIndex = (photoIndex + 1) % PHOTOS.length;
    applyPhoto();
  }
  function advanceQuote() {
    if (!quotes.length) return;
    quoteIndex = (quoteIndex + 1) % quotes.length;
    applyQuote();
  }
  function restartQuoteTimer() {
    if (quoteTimer) {
      clearInterval(quoteTimer);
      quoteTimer = null;
    }
    if (quotes.length < 2) return;
    quoteTimer = setInterval(advanceQuote, QUOTE_INTERVAL_MS);
  }
  function nextQuote() {
    advanceQuote();
    restartQuoteTimer();
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
    $("lyric-card").addEventListener("click", (e) => { e.stopPropagation(); nextQuote(); });
    $("lyric-card").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); nextQuote(); }
    });
    $("btn-photo").addEventListener("click", (e) => { e.stopPropagation(); nextPhoto(); });
  }

  function applyQuery() {
    const q = new URLSearchParams(location.search);
    const photo = q.get("photo");
    if (photo && PHOTOS.includes(photo)) photoIndex = PHOTOS.indexOf(photo);
    const quote = q.get("quote");
    if (quote !== null && /^\d+$/.test(quote)) quoteIndex = Number(quote);
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
    if ((DATA.quotes || []).length) quotes = DATA.quotes.slice();
    const q = new URLSearchParams(location.search).get("quote");
    if (q === null || !/^\d+$/.test(q)) {
      quoteIndex = quotes.length ? Math.floor(Math.random() * quotes.length) : 0;
    } else {
      quoteIndex = Number(q) % Math.max(1, quotes.length);
    }
    applyToday();
    applyQuote();
    restartQuoteTimer();
  }
  boot();
})();
