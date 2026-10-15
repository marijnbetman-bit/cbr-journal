/* =====================================================================
   CBR Journal · GAME MODE op de tradepagina (15 okt 2026)
   Alleen in game mode en alleen bij een bestaande trade (/trade?id=..): bovenaan een pixel-replay van de trade
   (candles, entry/exit, je echte SL/TP uit MT5) plus de kerncijfers. Het formulier eronder blijft zoals het was.
   ===================================================================== */
"use strict";
(function () {
  const id = +new URLSearchParams(location.search).get("id");
  if (!id || typeof GAME === "undefined" || !GAME.aan()) return;
  const C_ = { hi: "#3dff8a", red: "#ff5a4f", ink: "#d8ffe6", muted: "#6fae86", gold: "#ffd36b", cyan: "#7fe3ff", amber: "#ffb454" };
  const nl = (v, d = 2) => v == null ? "-" : Number(v).toLocaleString("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d });
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  async function start() {
    let d; try { d = await (await fetch("/api/game/replay/" + id)).json(); } catch (e) { return; }
    if (!d || d.error || !d.trade) return;
    const tr = d.trade, r = tr.resultaat_r;
    const host = document.createElement("section");
    host.className = "g-tradereplay";
    host.innerHTML = `<div class="g-tr-kop"><b>▶ REPLAY #${id} · ${esc(tr.datum)} ${esc(tr.tijd_entry || "")} ${tr.richting === "long" ? "▲ LONG" : "▼ SHORT"}</b>
        <span style="color:${r > 0 ? C_.hi : r < 0 ? C_.red : C_.muted}">${r == null ? "" : (r > 0 ? "+" : "") + nl(r) + "R"}</span>
        <span style="margin-left:auto"><button data-s="1">1X</button><button data-s="2" class="aan">2X</button><button data-s="4">4X</button>
        <button data-play="1">❚❚ PAUZE</button><a href="/game">← GAME OVERZICHT</a></span></div>
      <canvas width="960" height="300"></canvas>
      <div class="g-tr-info">ENTRY ${nl(tr.entry_prijs)} · SL ${nl(tr.sl_prijs)} · TP ${nl(tr.tp_prijs)} · EXIT ${nl(tr.exit_prijs)} ${esc(tr.exit_reden || "")}
        · GRADE ${esc(tr.grade || "?")}${tr.les ? " · LES: " + esc(tr.les) : ""}</div>`;
    const nav = document.getElementById("hoofdnav");
    (nav && nav.nextSibling ? nav.parentNode.insertBefore(host, nav.nextSibling) : document.body.prepend(host));
    const cv = host.querySelector("canvas"), g = cv.getContext("2d"), C = d.candles || [];
    const st = { i: 0, snel: 2, speelt: true };
    host.addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.s) { st.snel = +b.dataset.s; host.querySelectorAll("button[data-s]").forEach((x) => x.classList.toggle("aan", x === b)); }
      if (b.dataset.play) { if (st.i >= C.length) st.i = 0; st.speelt = !st.speelt; b.textContent = st.speelt ? "❚❚ PAUZE" : "▶ AFSPELEN"; } });
    function teken() {
      const W_ = cv.width, H_ = cv.height; g.fillStyle = "#02120a"; g.fillRect(0, 0, W_, H_);
      if (!C.length) { g.fillStyle = C_.muted; g.font = "22px VT323, monospace"; g.fillText("GEEN CANDLES VOOR DEZE TRADE IN MARKTDATA", 30, 60); return; }
      const p = C.flatMap((c) => [c[2], c[3]]).concat([tr.entry_prijs, tr.sl_prijs, tr.tp_prijs].filter((x) => x != null));
      const lo = Math.min(...p) - .5, hi = Math.max(...p) + .5, y = (v) => 12 + (hi - v) / (hi - lo) * (H_ - 34), bw = (W_ - 70) / C.length;
      const ie = C.findIndex((c) => c[0].slice(11, 16) >= (tr.tijd_entry || "").slice(0, 5)), ix = C.findIndex((c) => c[0].slice(11, 16) >= (tr.tijd_exit || "99"));
      const lijn = (v, kl, l) => { if (v == null) return; g.strokeStyle = kl; g.setLineDash([6, 4]); g.beginPath(); g.moveTo(0, y(v)); g.lineTo(W_ - 66, y(v)); g.stroke(); g.setLineDash([]);
        g.fillStyle = kl; g.font = "16px VT323, monospace"; g.fillText(l + " " + nl(v), W_ - 64, y(v) + 4); };
      lijn(tr.tp_prijs, C_.hi, "TP"); lijn(tr.sl_prijs, C_.red, "SL"); lijn(tr.entry_prijs, C_.ink, "IN");
      if (ie >= 0) { g.fillStyle = "rgba(127,227,255,.07)"; g.fillRect(ie * bw, 0, ((ix >= 0 ? ix : C.length) - ie) * bw, H_ - 20); }
      const n = Math.floor(st.i);
      for (let i = 0; i < n; i++) { const [, o, h, l, c] = C[i], x = i * bw; g.fillStyle = c >= o ? C_.hi : C_.red;
        g.fillRect(x + bw / 2 - .5, y(h), 1, Math.max(1, y(l) - y(h))); g.fillRect(x + 1, y(Math.max(o, c)), Math.max(1, bw - 2), Math.max(1, Math.abs(y(o) - y(c)))); }
      if (ie >= 0 && n > ie) { g.fillStyle = C_.gold; g.fillRect(ie * bw, y(tr.entry_prijs) - 3, 6, 6); g.font = "16px VT323, monospace"; g.fillText("ENTRY " + tr.tijd_entry, ie * bw + 8, y(tr.entry_prijs) - 6); }
      if (ix >= 0 && n > ix && tr.exit_prijs) { g.fillStyle = C_.cyan; g.fillRect(ix * bw, y(tr.exit_prijs) - 3, 6, 6); g.fillText("EXIT " + (tr.tijd_exit || ""), ix * bw + 8, y(tr.exit_prijs) + 16); }
      const ev = (d.events || []).map((e) => ({ ...e, i: C.findIndex((c) => c[0].slice(11, 16) >= e.ts.slice(11, 16)) })).filter((e) => e.i >= 0);
      const eind = Math.min(n, ix >= 0 ? ix + 1 : C.length);
      for (const [veld, kl] of [["sl", C_.red], ["tp", C_.hi]]) { g.strokeStyle = kl; g.lineWidth = 3; g.beginPath(); let s = false;
        ev.forEach((e, j) => { if (e[veld] == null || e.i >= eind) return; const x0 = e.i * bw, x1 = (j + 1 < ev.length ? Math.min(ev[j + 1].i, eind) : eind) * bw;
          if (!s) { g.moveTo(x0, y(e[veld])); s = true; } else g.lineTo(x0, y(e[veld])); g.lineTo(x1, y(e[veld])); });
        g.stroke(); g.lineWidth = 1; }
      for (const e of ev) if (e.i < n) { g.fillStyle = C_.amber; g.fillRect(e.i * bw, H_ - 18, 3, 8); }
      g.fillStyle = C_.muted; g.font = "15px VT323, monospace"; g.fillText(C[0][0].slice(11, 16), 2, H_ - 3); g.fillText(C[C.length - 1][0].slice(11, 16), W_ - 60, H_ - 3);
    }
    (function lus() { if (st.speelt && st.i < C.length) st.i = Math.min(C.length, st.i + .12 * st.snel); teken(); requestAnimationFrame(lus); })();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
