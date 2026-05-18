"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import type { Signal } from "@/lib/types";
import QRCode from "qrcode";

const T_VIOLET = {
  a1: "#c4b5fd", a2: "#7c3aed", a3: "#4c1d95",
  glow: "#6d28d9", bg1: "#08050f", bg2: "#0d0819",
  stripe: "#0e0920", card: "#ffffff07",
  orb: "#7c3aed",
};
const T_ROSE = {
  a1: "#fda4af", a2: "#f43f5e", a3: "#881337",
  glow: "#e11d48", bg1: "#0f0008", bg2: "#1a0010",
  stripe: "#200012", card: "#ffffff06",
  orb: "#e11d48",
};

type Mode = "roe" | "pnl" | "both";

function h2r(h: string, a = 1) {
  const r = parseInt(h.slice(1, 3), 16);
  const g = parseInt(h.slice(3, 5), 16);
  const b = parseInt(h.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function rr(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  r: number | { tl: number; tr: number; bl: number; br: number },
) {
  const rad = typeof r === "number"
    ? { tl: r, tr: r, bl: r, br: r }
    : r;
  ctx.beginPath();
  ctx.moveTo(x + rad.tl, y);
  ctx.lineTo(x + w - rad.tr, y);
  ctx.arcTo(x + w, y, x + w, y + rad.tr, rad.tr);
  ctx.lineTo(x + w, y + h - rad.br);
  ctx.arcTo(x + w, y + h, x + w - rad.br, y + h, rad.br);
  ctx.lineTo(x + rad.bl, y + h);
  ctx.arcTo(x, y + h, x, y + h - rad.bl, rad.bl);
  ctx.lineTo(x, y + rad.tl);
  ctx.arcTo(x, y, x + rad.tl, y, rad.tl);
  ctx.closePath();
}

function drawQR(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, size: number, color: string,
) {
  const cell = size / 8;
  const pat = [
    [1,1,1,1,0,1,1,1],[1,0,0,1,0,1,0,1],[1,0,1,1,1,0,0,1],[1,1,1,1,0,1,1,0],
    [0,1,0,0,1,0,1,1],[1,0,1,0,0,1,0,1],[1,1,1,1,0,0,1,0],[1,0,1,1,1,0,1,1],
  ];
  ctx.fillStyle = h2r(color, 0.45);
  pat.forEach((row, ri) =>
    row.forEach((c, ci) => {
      if (c) ctx.fillRect(x + ci * cell + 0.5, y + ri * cell + 0.5, cell - 1, cell - 1);
    }),
  );
  ctx.strokeStyle = h2r(color, 0.6);
  ctx.lineWidth = 1;
  [[0,0],[5,0],[0,5]].forEach(([cx, cy]) => {
    ctx.strokeRect(x + cx * cell, y + cy * cell, cell * 3, cell * 3);
  });
}

function makeNoise(W: number, H: number): HTMLCanvasElement {
  const off = document.createElement("canvas");
  off.width = W; off.height = H;
  const ox = off.getContext("2d")!;
  const id = ox.createImageData(W, H);
  for (let i = 0; i < id.data.length; i += 4) {
    const v = (Math.random() * 255) | 0;
    id.data[i] = id.data[i+1] = id.data[i+2] = v;
    id.data[i+3] = 10;
  }
  ox.putImageData(id, 0, 0);
  return off;
}

function smartFmt(n: number | null | undefined, withDollar = false): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  let str: string;
  if (abs === 0)         str = "0";
  else if (abs >= 10000) str = n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  else if (abs >= 1)     str = n.toFixed(4);
  else if (abs >= 0.01)  str = n.toFixed(6);
  else if (abs >= 0.0001) str = n.toFixed(8);
  else                   str = n.toPrecision(4);
  return withDollar ? `$${str}` : str;
}

function drawCoinIcon(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  ticker: string,
  T: typeof T_VIOLET,
  isLong: boolean,
) {
  const R = 44;
  ctx.save();
  ctx.save();
  ctx.strokeStyle = h2r(T.a1, 0.18);
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 5]);
  ctx.beginPath();
  ctx.arc(cx, cy, R + 14, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
  ctx.save();
  ctx.strokeStyle = h2r(T.a1, 0.35);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, R + 6, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
  [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].forEach((angle, i) => {
    const dotR = R + 6;
    const dx = cx + dotR * Math.cos(angle);
    const dy = cy + dotR * Math.sin(angle);
    ctx.beginPath();
    ctx.arc(dx, dy, i % 2 === 0 ? 3 : 2, 0, Math.PI * 2);
    ctx.fillStyle = i % 2 === 0 ? T.a1 : h2r(T.a1, 0.5);
    ctx.fill();
  });
  const grad = ctx.createRadialGradient(cx - 12, cy - 14, 6, cx, cy, R);
  grad.addColorStop(0, T.a1);
  grad.addColorStop(0.5, T.a2);
  grad.addColorStop(1, T.a3);
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.clip();
  ctx.strokeStyle = h2r("#ffffff", 0.05);
  ctx.lineWidth = 1;
  for (let ix = cx - R; ix <= cx + R; ix += 12) {
    ctx.beginPath(); ctx.moveTo(ix, cy - R); ctx.lineTo(ix, cy + R); ctx.stroke();
  }
  for (let iy = cy - R; iy <= cy + R; iy += 12) {
    ctx.beginPath(); ctx.moveTo(cx - R, iy); ctx.lineTo(cx + R, iy); ctx.stroke();
  }
  ctx.fillStyle = "rgba(255,255,255,0.13)";
  ctx.beginPath();
  ctx.arc(cx - 14, cy - 16, 20, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.strokeStyle = h2r("#ffffff", 0.25);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.6, 0, Math.PI * 2);
  ctx.stroke();
  const label = ticker.slice(0, 4).toUpperCase();
  const fs = label.length <= 3 ? 20 : 16;
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${fs}px "Bebas Neue",sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, cx, cy + 2);
  const badgeY = cy + R - 8;
  const sc = isLong ? "#4ade80" : "#f87171";
  ctx.beginPath();
  ctx.arc(cx, badgeY, 10, 0, Math.PI * 2);
  ctx.fillStyle = "#050505";
  ctx.fill();
  ctx.strokeStyle = h2r(sc, 0.6);
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = sc;
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(isLong ? "↗" : "↘", cx, badgeY);
  ctx.restore();
}

function drawPoster(
  canvas: HTMLCanvasElement,
  signal: Signal,
  mode: Mode,
  roeVal: number,
  pnlVal: number,
  leverage: number,
  currentPrice: number,
  platform = "SonneTrade",
  website = "sonnetrade.vercel.app",
  dpr = 1,
  candles: number[][] = [],
  qrImg: HTMLImageElement | null = null,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = 540, H = 800;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  const isPos = mode === "pnl" ? pnlVal >= 0 : roeVal >= 0;
  const T = isPos ? T_VIOLET : T_ROSE;
  const isLong = signal.decision === "LONG";
  const sc = isLong ? "#4ade80" : "#f87171";
  const pair  = signal.symbol.replace("_USDT", "");
  const quote = "USDT";

  rr(ctx, 0, 0, W, H, 20);
  const bgG = ctx.createLinearGradient(0, 0, 0, H);
  bgG.addColorStop(0, T.bg1); bgG.addColorStop(1, T.bg2);
  ctx.fillStyle = bgG; ctx.fill();
  const noise = makeNoise(W, H);
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.drawImage(noise, 0, 0); ctx.restore();
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.strokeStyle = T.stripe; ctx.lineWidth = 1;
  for (let i = -H; i < W + H; i += 32) {
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + H, H); ctx.stroke();
  }
  ctx.restore();
  [[W * 0.85, H * 0.15, 340, 0.22], [W * 0.1, H * 0.9, 220, 0.15], [-20, H * 0.45, 180, 0.1]].forEach(([ox, oy, or_, oa]) => {
    const g = ctx.createRadialGradient(ox, oy, 0, ox, oy, or_);
    g.addColorStop(0, h2r(T.glow, oa)); g.addColorStop(1, "transparent");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  });
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.save();
  ctx.translate(W - 30, 50); ctx.rotate(Math.PI / 8);
  ctx.strokeStyle = h2r(T.a1, 0.06); ctx.lineWidth = 1.5;
  for (let r2 = 40; r2 <= 140; r2 += 28) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3;
      i === 0 ? ctx.moveTo(r2 * Math.cos(a), r2 * Math.sin(a))
              : ctx.lineTo(r2 * Math.cos(a), r2 * Math.sin(a));
    }
    ctx.closePath(); ctx.stroke();
  }
  ctx.restore();
  ctx.strokeStyle = h2r(T.a1, 0.06); ctx.lineWidth = 1;
  for (let xi = 20; xi < 120; xi += 14) {
    for (let yi = H - 130; yi < H - 10; yi += 14) {
      ctx.beginPath(); ctx.moveTo(xi - 3, yi); ctx.lineTo(xi + 3, yi); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(xi, yi - 3); ctx.lineTo(xi, yi + 3); ctx.stroke();
    }
  }
  ctx.strokeStyle = h2r(T.a1, 0.16); ctx.lineWidth = 1; ctx.setLineDash([4, 8]);
  ctx.beginPath(); ctx.moveTo(-10, 90); ctx.lineTo(110, -10); ctx.stroke();
  ctx.setLineDash([]); ctx.restore();

  ctx.save();
  rr(ctx, 0, 0, W, 88, { tl: 20, tr: 20, bl: 0, br: 0 });
  const hG = ctx.createLinearGradient(0, 0, 0, 88);
  hG.addColorStop(0, h2r(T.a1, 0.1)); hG.addColorStop(1, "transparent");
  ctx.fillStyle = hG; ctx.fill(); ctx.restore();
  const hbG = ctx.createLinearGradient(0, 0, W, 0);
  hbG.addColorStop(0, "transparent"); hbG.addColorStop(0.2, h2r(T.a1, 0.35));
  hbG.addColorStop(0.8, h2r(T.a1, 0.35)); hbG.addColorStop(1, "transparent");
  ctx.strokeStyle = hbG; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, 88); ctx.lineTo(W, 88); ctx.stroke();
  ctx.save(); ctx.translate(32, 44);
  const hexG = ctx.createLinearGradient(-14, -14, 14, 14);
  hexG.addColorStop(0, T.a1); hexG.addColorStop(1, T.a2);
  ctx.fillStyle = hexG;
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 6;
    ctx.lineTo(16 * Math.cos(a), 16 * Math.sin(a));
  }
  ctx.closePath(); ctx.fill();
  ctx.strokeStyle = h2r("#ffffff", 0.3); ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 6;
    ctx.lineTo(9 * Math.cos(a), 9 * Math.sin(a));
  }
  ctx.closePath(); ctx.stroke(); ctx.restore();
  ctx.fillStyle = "#ffffff";
  ctx.font = "700 22px Outfit,sans-serif";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(platform.toUpperCase(), 56, 38);
  const pW = ctx.measureText(platform.toUpperCase()).width;
  ctx.fillStyle = T.a1;
  ctx.beginPath(); ctx.arc(60 + pW, 33, 4, 0, Math.PI * 2); ctx.fill();
  const ds = new Date(signal.timestamp).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  ctx.fillStyle = "#555555";
  ctx.font = '400 10px "JetBrains Mono",monospace';
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(ds, 57, 60);
  const sBg = isLong ? h2r("#4ade80", 0.12) : h2r("#f87171", 0.12);
  const sBd = isLong ? h2r("#4ade80", 0.45) : h2r("#f87171", 0.45);
  const pillW = 96, pillH = 30;
  rr(ctx, W - 28 - pillW, 28, pillW, pillH, 8);
  ctx.fillStyle = sBg; ctx.fill();
  ctx.strokeStyle = sBd; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = sc;
  ctx.font = "700 12px Outfit,sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText((isLong ? "▲ " : "▼ ") + signal.decision, W - 28 - pillW / 2, 43);

  const coinY = 110;
  const iCx = 60, iCy = coinY + 56;
  drawCoinIcon(ctx, iCx, iCy, pair, T, isLong);
  const pairX = 122;
  ctx.fillStyle = "#ffffff";
  ctx.font = '900 58px "Bebas Neue",sans-serif';
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  ctx.fillText(pair, pairX, coinY + 62);
  const bw = ctx.measureText(pair).width;
  ctx.fillStyle = "#3d3d3d";
  ctx.font = '300 26px "JetBrains Mono",monospace';
  ctx.fillText("/" + quote, pairX + bw + 4, coinY + 56);
  const tagY = coinY + 74;
  const tags = [
    { label: `${leverage}× LEVERAGE`, c: T.a1, bc: T.a2 },
    { label: isLong ? "LONG" : "SHORT", c: sc, bc: sc },
    { label: "FUTURES PERP", c: "#555", bc: "#333" },
  ];
  tags.forEach((tag, i) => {
    const tw = 86, tx = pairX + i * (tw + 7);
    rr(ctx, tx, tagY, tw, 22, 6);
    ctx.fillStyle = h2r(tag.bc, 0.14); ctx.fill();
    ctx.strokeStyle = h2r(tag.bc, 0.4); ctx.lineWidth = 0.75; ctx.stroke();
    ctx.fillStyle = tag.c;
    ctx.font = '500 9.5px "JetBrains Mono",monospace';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(tag.label, tx + tw / 2, tagY + 11);
  });
  ctx.textBaseline = "alphabetic";

  const divY = 240;
  const dg = ctx.createLinearGradient(0, 0, W, 0);
  dg.addColorStop(0, "transparent"); dg.addColorStop(0.12, h2r(T.a1, 0.7));
  dg.addColorStop(0.5, T.a1); dg.addColorStop(0.88, h2r(T.a1, 0.7));
  dg.addColorStop(1, "transparent");
  ctx.strokeStyle = dg; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(28, divY); ctx.lineTo(W - 28, divY); ctx.stroke();

  const roeStr = (roeVal >= 0 ? "+" : "") + roeVal.toLocaleString() + "%";
  const pnlStr = (pnlVal >= 0 ? "+" : "") + pnlVal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USDT";
  let statsYBase = 370;

  if (mode === "both") {
    let fs = 80;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(roeStr).width > W - 44 && fs > 40) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const roeY = 260 + fs;
    ctx.save();
    ctx.shadowColor = T.glow; ctx.shadowBlur = 50;
    ctx.fillStyle = T.a1; ctx.textAlign = "center";
    ctx.fillText(roeStr, W / 2, roeY);
    ctx.restore();
    const rg = ctx.createLinearGradient(0, roeY - fs, 0, roeY + 8);
    rg.addColorStop(0, "#ffffff"); rg.addColorStop(0.5, T.a1); rg.addColorStop(1, T.a2);
    ctx.fillStyle = rg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(roeStr, W / 2, roeY);
    ctx.fillStyle = "#888888";
    ctx.font = '500 10px "JetBrains Mono",monospace';
    ctx.textAlign = "center";
    ctx.fillText("R · E · T · U · R · N   O N   E · Q · U · I · T · Y", W / 2, roeY + 20);
    const pnlBY = roeY + 44;
    const pnlFmt = pnlStr;
    ctx.font = '700 28px "Bebas Neue",sans-serif';
    const pnlBW = ctx.measureText(pnlFmt).width + 48;
    rr(ctx, (W - pnlBW) / 2, pnlBY, pnlBW, 38, 10);
    ctx.fillStyle = h2r(isPos ? T_VIOLET.a2 : T_ROSE.a2, 0.15); ctx.fill();
    ctx.strokeStyle = h2r(T.a1, 0.35); ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = isPos ? "#4ade80" : "#f87171";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(pnlFmt, W / 2, pnlBY + 19);
    ctx.textBaseline = "alphabetic";
    statsYBase = pnlBY + 60;
  } else if (mode === "roe") {
    let fs = 108;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(roeStr).width > W - 44 && fs > 48) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const roeY = 258 + fs;
    ctx.save();
    ctx.shadowColor = T.glow; ctx.shadowBlur = 60;
    ctx.fillStyle = T.a1; ctx.textAlign = "center";
    ctx.fillText(roeStr, W / 2, roeY); ctx.restore();
    const rg = ctx.createLinearGradient(0, roeY - fs, 0, roeY + 8);
    rg.addColorStop(0, "#ffffff"); rg.addColorStop(0.5, T.a1); rg.addColorStop(1, T.a2);
    ctx.fillStyle = rg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(roeStr, W / 2, roeY);
    ctx.fillStyle = "#888888";
    ctx.font = '500 10px "JetBrains Mono",monospace';
    ctx.textAlign = "center";
    ctx.fillText("R · E · T · U · R · N   O N   E · Q · U · I · T · Y", W / 2, roeY + 22);
    statsYBase = roeY + 48;
  } else {
    let fs = 86;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(pnlStr).width > W - 44 && fs > 40) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const pnlY = 258 + fs;
    ctx.save();
    ctx.shadowColor = isPos ? "#4ade80" : "#f87171"; ctx.shadowBlur = 55;
    ctx.fillStyle = isPos ? "#4ade80" : "#f87171"; ctx.textAlign = "center";
    ctx.fillText(pnlStr, W / 2, pnlY); ctx.restore();
    const pg = ctx.createLinearGradient(0, pnlY - fs, 0, pnlY + 8);
    pg.addColorStop(0, "#ffffff");
    pg.addColorStop(0.5, isPos ? "#4ade80" : "#f87171");
    pg.addColorStop(1, isPos ? "#16a34a" : "#b91c1c");
    ctx.fillStyle = pg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(pnlStr, W / 2, pnlY);
    ctx.fillStyle = "#888888";
    ctx.font = '500 10px "JetBrains Mono",monospace';
    ctx.textAlign = "center";
    ctx.fillText("R · E · A · L · I · Z · E · D   P · R · O · F · I · T", W / 2, pnlY + 22);
    statsYBase = pnlY + 48;
  }

  const _cur   = currentPrice > 0 ? currentPrice : (signal.current_price ?? null);
  const _entry = signal.entry != null ? Number(signal.entry) : null;
  const _tp    = signal.tp    != null ? Number(signal.tp)    : null;
  const _sl    = signal.sl    != null ? Number(signal.sl)    : null;
  const statDefs = [
    { label: "CURRENT",     val: (_cur != null && _cur > 0) ? `$${smartFmt(_cur)}` : "—", c: "#93c5fd" },
    { label: "ENTRY",       val: (_entry != null && _entry > 0) ? `$${smartFmt(_entry)}` : "—", c: "#e2e8f0" },
    { label: "TAKE PROFIT", val: (_tp != null && _tp > 0) ? `$${smartFmt(_tp)}` : "—", c: "#86efac" },
    { label: "STOP LOSS",   val: (_sl != null && _sl > 0) ? `$${smartFmt(_sl)}` : "—", c: "#fca5a5" },
  ];
  const gap2 = 7;
  const cW = (W - 56 - gap2 * (statDefs.length - 1)) / statDefs.length;
  statDefs.forEach((s, i) => {
    const sx = 28 + i * (cW + gap2), sy = statsYBase, sh = 68;
    rr(ctx, sx, sy, cW, sh, 12);
    ctx.fillStyle = "rgba(255,255,255,0.04)"; ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.09)"; ctx.lineWidth = 1; ctx.stroke();
    rr(ctx, sx, sy, cW, 3, { tl: 12, tr: 12, bl: 0, br: 0 });
    ctx.fillStyle = h2r(T.a1, 0.6); ctx.fill();
    ctx.fillStyle = "#909090";
    ctx.font = '400 9px "JetBrains Mono",monospace';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(s.label, sx + cW / 2, sy + 22);
    let vfs = 14;
    ctx.font = `700 ${vfs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(s.val).width > cW - 8 && vfs > 9) {
      vfs -= 1; ctx.font = `700 ${vfs}px "Bebas Neue",sans-serif`;
    }
    ctx.fillStyle = s.c;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(s.val, sx + cW / 2, sy + 50);
  });
  ctx.textBaseline = "alphabetic";

  const arcY = statsYBase + 84;
  const chX = 28, chW = W - 56, chH = 130;
  const _entry2 = signal.entry != null ? Number(signal.entry) : null;
  const _tp2    = signal.tp    != null ? Number(signal.tp)    : null;
  const _sl2    = signal.sl    != null ? Number(signal.sl)    : null;
  const _cur2   = currentPrice > 0 ? currentPrice : (signal.current_price ?? null);

  // Determine trade outcome for chart direction
  const isLongSignal  = signal.decision === "LONG";
  const pnlNumber     = mode === "pnl" ? pnlVal : roeVal;
  const isProfit      = pnlNumber >= 0;
  const isRekt        = !isProfit; // loss = REKT mode

  let prices: number[] = [];
  let candleTimes: number[] = [];
  if (candles && candles.length > 2) {
    prices      = candles.map(c => parseFloat(String(c[4])));
    candleTimes = candles.map(c => Number(c[0]));
  } else if (!isRekt) {
    // Realistic swing-structure chart
    // LONG  profit = Higher Highs + Higher Lows (uptrend)
    // SHORT profit = Lower  Highs + Lower  Lows (downtrend)
    const base = _entry2 ?? (_cur2 ?? 100);
    let seed = 0;
    const seedStr = String(signal.id ?? signal.symbol ?? "x");
    for (let k = 0; k < seedStr.length; k++) seed = (seed * 31 + seedStr.charCodeAt(k)) & 0xfffff;
    const rng = () => { seed = (seed * 1664525 + 1013904223) & 0xffffffff; return (seed >>> 0) / 0xffffffff; };

    const trendDir    = isLongSignal ? 1 : -1;
    const numSwings   = 5;
    const impulseSize = 0.006 + rng() * 0.003;
    const retracePct  = 0.38 + rng() * 0.22;
    const pivots: number[] = [base];
    let pivCur = base;
    for (let s = 0; s < numSwings; s++) {
      const impulse = pivCur * impulseSize * (0.7 + rng() * 0.6);
      pivCur = pivCur + trendDir * impulse;
      pivots.push(pivCur);
      const retrace = impulse * retracePct * (0.8 + rng() * 0.4);
      pivCur = pivCur - trendDir * retrace;
      pivots.push(pivCur);
    }
    const target = (_cur2 && _cur2 > 0) ? _cur2 : pivCur + trendDir * pivCur * impulseSize;
    pivots.push(target);

    const N = 52;
    const segN = Math.floor(N / pivots.length) + 1;
    const raw: number[] = [];
    for (let p = 0; p < pivots.length - 1; p++) {
      const from = pivots[p], to = pivots[p + 1];
      const steps = p === pivots.length - 2 ? segN + (N - segN * (pivots.length - 1)) : segN;
      for (let s = 0; s < steps; s++) {
        const tt = s / steps;
        const ease = tt < 0.5 ? 4 * tt * tt * tt : 1 - Math.pow(-2 * tt + 2, 3) / 2;
        raw.push(from + (to - from) * ease + (rng() - 0.5) * from * 0.0012);
      }
    }
    prices = raw.slice(0, N);
    while (prices.length < N) prices.push(prices[prices.length - 1]);
    if (_cur2 && _cur2 > 0) {
      prices[prices.length - 1] = _cur2;
      for (let i = prices.length - 6; i < prices.length - 1; i++) {
        const tt2 = (i - (prices.length - 6)) / 5;
        prices[i] = prices[i] * (1 - tt2) + _cur2 * tt2;
      }
    }
  }
  const n = prices.length;
  const allPr: number[] = [...prices];
  if (_entry2 && _entry2 > 0) allPr.push(_entry2);
  if (_cur2   && _cur2   > 0) allPr.push(_cur2);
  if (_tp2    && _tp2    > 0) allPr.push(_tp2);
  if (_sl2    && _sl2    > 0) allPr.push(_sl2);
  const rawMin = allPr.length ? Math.min(...allPr) : 0;
  const rawMax = allPr.length ? Math.max(...allPr) : 1;
  const rawRng = rawMax - rawMin || rawMax * 0.02 || 1;
  const pad2   = rawRng * 0.18;
  const yMin2  = rawMin - pad2, yMax2 = rawMax + pad2, yRng2 = yMax2 - yMin2;
  const histW = chW - 52;
  const nowX  = chX + chW - 16;
  const toXC = (i: number) => chX + 12 + (i / Math.max(n - 1, 1)) * histW;
  const toY2 = (v: number) =>
    arcY + chH - 10 - ((v - yMin2) / yRng2) * (chH - 20);
  const pts = prices.map((v, i) => ({ x: toXC(i), y: toY2(v) }));
  const liveY = _cur2 && _cur2 > 0 ? toY2(_cur2) : pts.length ? pts[pts.length - 1].y : arcY + chH / 2;

  function smoothPath(c: CanvasRenderingContext2D, points: {x:number;y:number}[], tension = 0.35) {
    if (!points.length) return;
    c.moveTo(points[0].x, points[0].y);
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(i - 1, 0)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(i + 2, points.length - 1)];
      const cp1x = p1.x + (p2.x - p0.x) * tension;
      const cp1y = p1.y + (p2.y - p0.y) * tension;
      const cp2x = p2.x - (p3.x - p1.x) * tension;
      const cp2y = p2.y - (p3.y - p1.y) * tension;
      c.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
    }
  }

  // ── CHART CONTAINER ─────────────────────────────────────────────────────────
  rr(ctx, chX, arcY, chW, chH, 14);
  ctx.fillStyle = "rgba(255,255,255,0.016)"; ctx.fill();
  ctx.strokeStyle = isRekt ? "rgba(248,113,113,0.18)" : "rgba(255,255,255,0.055)";
  ctx.lineWidth = 1; ctx.stroke();
  ctx.save();
  rr(ctx, chX, arcY, chW, chH, 14); ctx.clip();

  if (isRekt) {
    // ── REKT MODE ─────────────────────────────────────────────────────────────
    // Dramatic red glow background
    const rektBg = ctx.createRadialGradient(chX + chW/2, arcY + chH/2, 10, chX + chW/2, arcY + chH/2, chW * 0.75);
    rektBg.addColorStop(0, "rgba(185,28,28,0.22)");
    rektBg.addColorStop(0.5, "rgba(127,0,0,0.12)");
    rektBg.addColorStop(1, "transparent");
    ctx.fillStyle = rektBg; ctx.fillRect(chX, arcY, chW, chH);

    // Diagonal danger stripes
    ctx.strokeStyle = "rgba(248,113,113,0.06)"; ctx.lineWidth = 1;
    for (let si = -chH; si < chW + chH; si += 22) {
      ctx.beginPath(); ctx.moveTo(chX + si, arcY); ctx.lineTo(chX + si + chH, arcY + chH); ctx.stroke();
    }

    // Draw a crashing chart line that plummets
    const rektN = 32;
    const rektBase = _entry2 ?? (_cur2 ?? 100);
    let rektSeed = 0;
    const rektStr = String(signal.id ?? "rekt");
    for (let k = 0; k < rektStr.length; k++) rektSeed = (rektSeed * 31 + rektStr.charCodeAt(k)) & 0xfffff;
    const rektRng = () => { rektSeed = (rektSeed * 1664525 + 1013904223) & 0xffffffff; return (rektSeed >>> 0) / 0xffffffff; };

    const rektPrices: number[] = [rektBase];
    for (let i = 1; i < rektN; i++) {
      const crash = -0.003 * (0.8 + rektRng() * 0.8);
      const noise = ((rektRng() + rektRng()) / 2 - 0.5) * 0.001;
      rektPrices.push(rektPrices[i-1] * (1 + crash + noise));
    }
    const rMin = Math.min(...rektPrices) * 0.97, rMax = Math.max(...rektPrices) * 1.03;
    const rRng = rMax - rMin || 1;
    const toYR = (v: number) => arcY + chH - 8 - ((v - rMin) / rRng) * (chH - 18);
    const rPts = rektPrices.map((v, i) => ({ x: chX + 10 + (i / (rektN - 1)) * (chW - 26), y: toYR(v) }));

    // Area fill under crash line
    ctx.beginPath();
    smoothPath(ctx, rPts);
    ctx.lineTo(rPts[rPts.length - 1].x, arcY + chH - 3);
    ctx.lineTo(rPts[0].x, arcY + chH - 3);
    ctx.closePath();
    const crashFill = ctx.createLinearGradient(0, arcY, 0, arcY + chH);
    crashFill.addColorStop(0, "rgba(248,113,113,0.12)");
    crashFill.addColorStop(1, "rgba(185,28,28,0.02)");
    ctx.fillStyle = crashFill; ctx.fill();

    // Glow stroke
    ctx.save();
    ctx.shadowColor = "#f87171"; ctx.shadowBlur = 10;
    ctx.beginPath(); smoothPath(ctx, rPts);
    ctx.strokeStyle = "rgba(248,113,113,0.4)"; ctx.lineWidth = 3.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
    ctx.restore();
    ctx.beginPath(); smoothPath(ctx, rPts);
    ctx.strokeStyle = "#f87171"; ctx.lineWidth = 1.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();

    ctx.restore(); // end clip

    // ── REKT TEXT OVERLAY ────────────────────────────────────────────────────
    // Outer glow layer
    ctx.save();
    ctx.shadowColor = "#f87171";
    ctx.shadowBlur = 48;
    ctx.font = '900 96px "Bebas Neue",sans-serif';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(248,113,113,0.18)";
    ctx.fillText("REKT", chX + chW / 2, arcY + chH / 2);
    ctx.restore();
    // Main REKT text with luxury gradient
    const rektGrad = ctx.createLinearGradient(chX + chW * 0.15, arcY + chH * 0.25, chX + chW * 0.85, arcY + chH * 0.75);
    rektGrad.addColorStop(0, "#ffffff");
    rektGrad.addColorStop(0.25, "#fca5a5");
    rektGrad.addColorStop(0.55, "#ef4444");
    rektGrad.addColorStop(1, "#7f1d1d");
    ctx.save();
    ctx.shadowColor = "#ef4444"; ctx.shadowBlur = 28;
    ctx.font = '900 96px "Bebas Neue",sans-serif';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = rektGrad;
    ctx.fillText("REKT", chX + chW / 2, arcY + chH / 2);
    ctx.restore();
    // Italic subtext
    ctx.save();
    ctx.font = '600 italic 10px "JetBrains Mono",monospace';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(248,113,113,0.55)";
    ctx.fillText("STOPPED OUT · BETTER LUCK NEXT TIME", chX + chW / 2, arcY + chH - 14);
    ctx.restore();

  } else {
    // ── NORMAL PROFIT CHART ──────────────────────────────────────────────────
    // Grid lines
    ctx.strokeStyle = "rgba(255,255,255,0.025)"; ctx.lineWidth = 1;
    [0.25, 0.5, 0.75].forEach(p => {
      const ly = arcY + chH * p;
      ctx.beginPath(); ctx.moveTo(chX + 10, ly); ctx.lineTo(chX + chW - 10, ly); ctx.stroke();
    });

    // TP zone highlight
    if (_tp2 && _tp2 > 0 && _entry2 && _entry2 > 0) {
      const y1 = Math.min(toY2(_tp2), toY2(_entry2));
      const y2 = Math.max(toY2(_tp2), toY2(_entry2));
      const zg = ctx.createLinearGradient(0, y1, 0, y2);
      zg.addColorStop(0, "rgba(74,222,128,0.09)"); zg.addColorStop(1, "rgba(74,222,128,0.02)");
      ctx.fillStyle = zg;
      ctx.fillRect(chX + 10, Math.max(y1, arcY + 4), chW - 20,
        Math.min(y2, arcY + chH - 4) - Math.max(y1, arcY + 4));
    }
    // SL zone highlight
    if (_sl2 && _sl2 > 0 && _entry2 && _entry2 > 0) {
      const y1 = Math.min(toY2(_sl2), toY2(_entry2));
      const y2 = Math.max(toY2(_sl2), toY2(_entry2));
      const zg = ctx.createLinearGradient(0, y1, 0, y2);
      zg.addColorStop(0, "rgba(248,113,113,0.02)"); zg.addColorStop(1, "rgba(248,113,113,0.09)");
      ctx.fillStyle = zg;
      ctx.fillRect(chX + 10, Math.max(y1, arcY + 4), chW - 20,
        Math.min(y2, arcY + chH - 4) - Math.max(y1, arcY + 4));
    }

    // TP / SL / ENTRY horizontal lines
    const hlines = [
      { price: _tp2,    color: "rgba(74,222,128,0.4)",   label: "TP", dash: [4,5] as number[] },
      { price: _sl2,    color: "rgba(248,113,113,0.4)",  label: "SL", dash: [4,5] as number[] },
      { price: _entry2, color: "rgba(255,255,255,0.18)", label: "",   dash: [2,7] as number[] },
    ];
    hlines.forEach(({ price, color, label, dash }) => {
      if (!price || price <= 0) return;
      const ly = toY2(price);
      if (ly <= arcY + 5 || ly >= arcY + chH - 5) return;
      ctx.strokeStyle = color; ctx.lineWidth = 0.75;
      ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(chX + 10, ly); ctx.lineTo(chX + chW - 10, ly); ctx.stroke();
      ctx.setLineDash([]);
      if (label) {
        ctx.fillStyle = color.replace(/[\d.]+\)$/, "0.85)");
        ctx.font = '500 6.5px "JetBrains Mono",monospace';
        ctx.textAlign = "left"; ctx.textBaseline = "middle";
        ctx.fillText(label, chX + 14, ly - 5);
        ctx.textBaseline = "alphabetic";
      }
    });

    // Area fill
    const areaGrad = ctx.createLinearGradient(0, arcY, 0, arcY + chH);
    areaGrad.addColorStop(0, h2r(T.a2, 0.30));
    areaGrad.addColorStop(0.65, h2r(T.a2, 0.09));
    areaGrad.addColorStop(1, "transparent");
    if (pts.length > 0) {
      ctx.beginPath();
      smoothPath(ctx, pts);
      ctx.lineTo(nowX, liveY);
      ctx.lineTo(nowX, arcY + chH - 4);
      ctx.lineTo(pts[0].x, arcY + chH - 4);
      ctx.closePath();
      ctx.fillStyle = areaGrad; ctx.fill();
    }

    // Glow stroke
    if (pts.length > 0) {
      ctx.save();
      ctx.shadowColor = T.a1; ctx.shadowBlur = 10;
      ctx.beginPath(); smoothPath(ctx, pts);
      ctx.strokeStyle = h2r(T.a1, 0.35); ctx.lineWidth = 4.5;
      ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
      ctx.restore();
      // Main line
      ctx.beginPath(); smoothPath(ctx, pts);
      ctx.strokeStyle = T.a1; ctx.lineWidth = 1.8;
      ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
    }

    // Dashed extension to live price dot
    if (pts.length > 0) {
      const lastPt = pts[pts.length - 1];
      ctx.setLineDash([2, 4]);
      ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(lastPt.x, lastPt.y); ctx.lineTo(nowX, liveY);
      ctx.stroke(); ctx.setLineDash([]);
    }

    // Entry marker dot
    if (_entry2 && _entry2 > 0 && n > 2) {
      let entXIdx = Math.floor(n * 0.35);
      if (candleTimes.length > 0 && signal.timestamp) {
        let minDiff = Infinity;
        candleTimes.forEach((t, idx) => {
          const diff = Math.abs(t - signal.timestamp);
          if (diff < minDiff) { minDiff = diff; entXIdx = idx; }
        });
      }
      const entMX = toXC(entXIdx);
      const entMY = toY2(_entry2);
      ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 1;
      ctx.setLineDash([2, 5]);
      ctx.beginPath(); ctx.moveTo(entMX, arcY + 5); ctx.lineTo(entMX, arcY + chH - 5); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.arc(entMX, entMY, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = T.bg1; ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.beginPath(); ctx.arc(entMX, entMY, 2, 0, Math.PI * 2);
      ctx.fillStyle = T.a1; ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.3)";
      ctx.font = '400 6px "JetBrains Mono",monospace';
      ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.fillText("ENTRY", entMX, arcY + chH - 2);
      ctx.textBaseline = "alphabetic";
    }

    // Live price dot + label
    if (_cur2 && _cur2 > 0) {
      ctx.save();
      ctx.shadowColor = T.a1; ctx.shadowBlur = 18;
      ctx.beginPath(); ctx.arc(nowX, liveY, 7, 0, Math.PI * 2);
      ctx.fillStyle = h2r(T.a1, 0.22); ctx.fill();
      ctx.restore();
      ctx.beginPath(); ctx.arc(nowX, liveY, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = T.a1; ctx.fill();
      ctx.beginPath(); ctx.arc(nowX, liveY, 2, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff"; ctx.fill();
      const prLabel = `$${smartFmt(_cur2)}`;
      ctx.font = '600 7.5px "JetBrains Mono",monospace';
      const lblW = ctx.measureText(prLabel).width;
      let pillX = nowX - lblW - 16;
      if (pillX < chX + 14) pillX = nowX + 10;
      const pillY = liveY - 6.5;
      rr(ctx, pillX - 5, pillY - 1, lblW + 10, 14, 3);
      ctx.fillStyle = h2r(T.a3, 0.9); ctx.fill();
      ctx.strokeStyle = h2r(T.a1, 0.45); ctx.lineWidth = 0.5; ctx.stroke();
      ctx.fillStyle = T.a1;
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText(prLabel, pillX, pillY + 6);
      ctx.textBaseline = "alphabetic";
    }
    ctx.restore(); // end clip
  }

  const botBarH = 80;
  const botY = arcY + chH + 24;
  rr(ctx, 28, botY, W - 56, botBarH, 14);
  ctx.fillStyle = h2r(T.a1, 0.05); ctx.fill();
  ctx.strokeStyle = h2r(T.a1, 0.12); ctx.lineWidth = 1; ctx.stroke();
  ctx.save(); rr(ctx, 28, botY, W - 56, botBarH, 14); ctx.clip();
  ctx.strokeStyle = h2r(T.a1, 0.04); ctx.lineWidth = 1;
  for (let ix2 = 28; ix2 < W - 28; ix2 += 18) {
    ctx.beginPath(); ctx.moveTo(ix2, botY); ctx.lineTo(ix2, botY + botBarH); ctx.stroke();
  }
  ctx.restore();
  ctx.fillStyle = "#5a5a5a";
  ctx.font = '400 9px "JetBrains Mono",monospace';
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText("Auto-generated via AI analysis", 44, botY + 20);
  const chipPad = 12, chipH = 28;
  const chipX = 30, chipY = botY + 38;
  const urlText = "http://" + website.replace(/^https?:\/\//, "");
  ctx.font = '500 11px "JetBrains Mono",monospace';
  const urlTextW = ctx.measureText(urlText).width;
  const globeIconW = 16;
  const chipW = chipPad * 2 + globeIconW + urlTextW + 4;
  rr(ctx, chipX, chipY, chipW, chipH, 7);
  ctx.fillStyle = h2r(T.a1, 0.1); ctx.fill();
  ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 1; ctx.stroke();
  const globeX = chipX + chipPad + 4, globeY2 = chipY + chipH / 2;
  ctx.strokeStyle = T.a1; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(globeX, globeY2, 6, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(globeX, globeY2, 3.5, 6, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(globeX - 6.5, globeY2); ctx.lineTo(globeX + 6.5, globeY2); ctx.stroke();
  ctx.fillStyle = T.a1;
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(urlText, chipX + chipPad + globeIconW + 4, chipY + chipH / 2);
  const qrSize = 56, qrX = W - 28 - qrSize, qrY = botY + Math.round((botBarH - qrSize) / 2);
  if (qrImg) {
    ctx.save();
    ctx.globalAlpha = 0.75;
    ctx.drawImage(qrImg, qrX, qrY, qrSize, qrSize);
    ctx.globalAlpha = 1;
    ctx.restore();
  } else {
    drawQR(ctx, qrX, qrY, qrSize, T.a1);
  }
  const botStrip = ctx.createLinearGradient(0, 0, W, 0);
  botStrip.addColorStop(0, "transparent"); botStrip.addColorStop(0.2, T.a1);
  botStrip.addColorStop(0.8, T.a1); botStrip.addColorStop(1, "transparent");
  ctx.fillStyle = botStrip; ctx.fillRect(0, H - 4, W, 4);
  const vig = ctx.createRadialGradient(W/2, H/2, H*0.3, W/2, H/2, H*0.75);
  vig.addColorStop(0, "transparent"); vig.addColorStop(1, "rgba(0,0,0,0.35)");
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.fillStyle = vig; ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

function calcAutoROE(signal: Signal, leverage: number, livePrice?: number): number {
  if (signal.pnl_pct != null) {
    return parseFloat((Number(signal.pnl_pct) * leverage).toFixed(2));
  }
  const entry = Number(signal.entry ?? signal.current_price);
  const cur   = livePrice ?? Number(signal.current_price);
  if (!entry || !cur) return 0;
  const movePct = signal.decision === "LONG"
    ? ((cur - entry) / entry) * 100
    : ((entry - cur) / entry) * 100;
  return parseFloat((movePct * leverage).toFixed(2));
}

function calcAutoPnL(signal: Signal, leverage: number, entryUsdt = 100, livePrice?: number): number {
  if (signal.pnl_usdt != null) return Number(signal.pnl_usdt);
  const entry = Number(signal.entry ?? signal.current_price);
  const cur   = livePrice ?? Number(signal.current_price);
  if (!entry || !cur) return 0;
  const movePct = signal.decision === "LONG"
    ? (cur - entry) / entry
    : (entry - cur) / entry;
  return parseFloat((entryUsdt * leverage * movePct).toFixed(2));
}

function getBotWsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host  = window.location.host;
  return `${proto}//${host}/api/bot/ws`;
}

function PosterModal({
  signal, leverage, entryUsdt = 20, onClose,
}: {
  signal: Signal;
  leverage: number;
  entryUsdt?: number;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mode, setMode]     = useState<Mode>("roe");
  const [sharing, setSharing] = useState(false);
  const [mounted, setMounted] = useState(false);
  const isClosed = signal.status === "CLOSED" || signal.status === "INVALIDATED";
  const sym      = signal.symbol;

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 10);
    return () => clearTimeout(t);
  }, []);

  const [qrImg, setQrImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    const url = "https://sonnetrade.vercel.app";
    QRCode.toDataURL(url, {
      width: 112,
      margin: 1,
      color: { dark: "#ffffff", light: "#00000000" },
    }).then((dataUrl) => {
      const img = new window.Image();
      img.onload = () => setQrImg(img);
      img.src = dataUrl;
    }).catch(() => {});
  }, []);

  const [candles, setCandles] = useState<number[][]>([]);
  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const res  = await fetch(`/api/market/candles/${sym}?granularity=5m&limit=60`);
        const json = await res.json();
        const data = json.data ?? [];
        if (Array.isArray(data) && data.length > 2) setCandles(data);
      } catch {}
    };
    fetchCandles();
    const t = setInterval(fetchCandles, 30_000);
    return () => clearInterval(t);
  }, [sym]);

  const [livePrice, setLivePrice] = useState<number>(
    isClosed && signal.closed_price
      ? Number(signal.closed_price)
      : Number(signal.current_price) || 0
  );
  const [priceSource, setPriceSource] = useState<"ws" | "rest" | "closed" | "initial">(
    isClosed ? "closed" : "initial"
  );

  useEffect(() => {
    if (isClosed) return;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let alive = true;
    const connect = () => {
      if (!alive) return;
      const url = getBotWsUrl();
      if (!url) return;
      ws = new WebSocket(url);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data as string);
          if (msg.event === "price_tick" && msg.data?.symbol === sym) {
            const p = Number(msg.data.price);
            if (p > 0) { setLivePrice(p); setPriceSource("ws"); }
          }
          if (
            (msg.event === "signal_closed" || msg.event === "signal_invalidated") &&
            msg.data?.symbol === sym
          ) {
            const p = Number(msg.data.price ?? msg.data.closed_price);
            if (p > 0) setLivePrice(p);
          }
        } catch {}
      };
      ws.onerror = () => {};
      ws.onclose = () => {
        if (alive) reconnectTimer = setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      alive = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [sym, isClosed]);

  useEffect(() => {
    if (isClosed) return;
    const fetchPrice = async () => {
      try {
        const res  = await fetch(`/api/market/ticker/${sym}`);
        const json = await res.json();
        const d    = json.data ?? {};
        const p    = parseFloat(d.lastPr ?? d.last ?? d.lastPrice ?? "0");
        if (p > 0) {
          setLivePrice(p);
          setPriceSource(src => src === "ws" ? "ws" : "rest");
        }
      } catch {}
    };
    fetchPrice();
    const timer = setInterval(fetchPrice, 3000);
    return () => clearInterval(timer);
  }, [sym, isClosed]);

  const roeVal = calcAutoROE(signal, leverage, livePrice > 0 ? livePrice : undefined);
  const pnlVal = calcAutoPnL(signal, leverage, entryUsdt, livePrice > 0 ? livePrice : undefined);

  useEffect(() => {
    if (!canvasRef.current) return;
    drawPoster(canvasRef.current, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 1, candles, qrImg);
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice, candles, qrImg]);

  // Pre-render HD blob in background as soon as poster is ready
  const [hdBlob, setHdBlob] = useState<Blob | null>(null);
  const [hdReady, setHdReady] = useState(false);
  useEffect(() => {
    if (!mounted) return;
    setHdReady(false);
    const render = () => {
      const hd = document.createElement("canvas");
      drawPoster(hd, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 2, candles, qrImg);
      hd.toBlob((blob) => { if (blob) { setHdBlob(blob); setHdReady(true); } }, "image/png");
    };
    let idleId: number | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    if (typeof requestIdleCallback !== "undefined") {
      idleId = requestIdleCallback(render, { timeout: 1500 });
    } else {
      timeoutId = setTimeout(render, 300);
    }
    return () => {
      if (idleId !== undefined) cancelIdleCallback(idleId);
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice, candles, qrImg, mounted]);

  const getHDBlob = useCallback((): Promise<Blob> => {
    if (hdBlob) return Promise.resolve(hdBlob);
    return new Promise((resolve, reject) => {
      const hd = document.createElement("canvas");
      drawPoster(hd, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 2, candles, qrImg);
      hd.toBlob((blob) => { if (blob) resolve(blob); else reject(new Error("Canvas toBlob failed")); }, "image/png");
    });
  }, [hdBlob, signal, mode, roeVal, pnlVal, leverage, livePrice, candles, qrImg]);

  const handleSave = useCallback(async () => {
    const blob = await getHDBlob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `sonnetrade-${signal.symbol}-poster.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [getHDBlob, signal.symbol]);

  const handleShare = useCallback(async () => {
    setSharing(true);
    try {
      const blob = await getHDBlob();
      const file = new File([blob], `sonnetrade-${signal.symbol}.png`, { type: "image/png" });
      if (navigator.share && navigator.canShare({ files: [file] })) {
        await navigator.share({
          title: `${signal.symbol} ${signal.decision} Signal — SonneTrade`,
          text:  `Check out this ${signal.decision} signal on ${signal.symbol}!`,
          files: [file],
        });
      } else {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
        setTimeout(() => URL.revokeObjectURL(url), 30_000);
      }
    } catch (e) {
      console.error("Share failed", e);
    } finally {
      setSharing(false);
    }
  }, [getHDBlob, signal.symbol, signal.decision]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className={`fixed inset-0 z-[9999] flex items-end sm:items-center justify-center bg-black/85 backdrop-blur-md sm:p-4 transition-opacity duration-300 ${mounted ? "opacity-100" : "opacity-0"}`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className={`bg-[#0a0a0f] border border-[#d4a847]/20 sm:rounded-3xl rounded-t-3xl w-full sm:max-w-3xl max-h-[95dvh] sm:max-h-[90vh] overflow-y-auto overscroll-contain [&]:[-webkit-overflow-scrolling:touch] shadow-[0_0_80px_rgba(212,168,71,0.12)] transition-all duration-500 ${mounted ? "translate-y-0 scale-100" : "translate-y-8 scale-95"}`}
      >
        {/* Luxury Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-[#d4a847]/10 relative">
          <div className="flex items-center gap-3">
            <div className="w-1 h-6 rounded-full bg-gradient-to-b from-[#d4a847] to-[#d4a847]/20" />
            <div>
              <h3 className="text-sm font-bold font-mono text-white tracking-widest">SHARE POSTER</h3>
              <p className="text-[10px] font-mono text-white/30 tracking-wider mt-0.5">
                {signal.symbol.replace("_USDT", "")}/USDT · {signal.decision} · {isClosed ? "CLOSED" : "LIVE"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="group w-9 h-9 rounded-full glass border border-white/10 flex items-center justify-center text-white/40 hover:text-white hover:border-[#d4a847]/50 hover:bg-[#d4a847]/10 hover:shadow-[0_0_20px_rgba(212,168,71,0.2)] transition-all duration-300"
            aria-label="Close"
          >
            <svg className="w-4 h-4 group-hover:rotate-90 transition-transform duration-300" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex flex-col-reverse md:flex-row gap-0">
          {/* Controls Panel */}
          <div className="w-full md:w-64 shrink-0 p-5 sm:p-6 border-t md:border-t-0 md:border-r border-white/[0.06] flex flex-col gap-5 bg-black/20">
            <div className="flex flex-col gap-2">
              <span className="text-[9px] font-mono uppercase tracking-[0.25em] text-[#d4a847]/70">Display Mode</span>
              <div className="flex flex-row md:flex-col gap-1.5">
                {(["roe", "pnl", "both"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`flex-1 md:flex-none px-3 py-2.5 rounded-xl text-[11px] font-mono font-medium text-left transition-all border ${
                      mode === m
                        ? "bg-[#d4a847]/15 border-[#d4a847]/40 text-[#d4a847] shadow-[0_0_12px_rgba(212,168,71,0.15)]"
                        : "border-white/[0.06] text-white/30 hover:text-white/60 hover:border-white/10 hover:bg-white/[0.03]"
                    }`}
                  >
                    {m === "roe"  && "📊 ROE only"}
                    {m === "pnl"  && "💰 PnL only"}
                    {m === "both" && "✨ ROE + PnL"}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2 bg-white/[0.02] rounded-2xl p-4 border border-white/[0.06]">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/30">
                  {isClosed ? "Final Result" : "Live Values"}
                </span>
                {!isClosed && (
                  <span className="flex items-center gap-1.5 text-[9px] font-mono text-[#d4a847]/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#d4a847] animate-pulse" />
                    {priceSource === "ws" ? "websocket" : priceSource === "rest" ? "rest api" : "—"}
                  </span>
                )}
                {isClosed && (
                  <span className="text-[9px] font-mono text-white/20 uppercase tracking-wider">Archived</span>
                )}
              </div>
              <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                <span className="text-[11px] font-mono text-white/40">Price</span>
                <span className="text-xs font-mono font-semibold text-[#93c5fd]">${smartFmt(livePrice > 0 ? livePrice : signal.current_price)}</span>
              </div>
              {(mode === "roe" || mode === "both") && (
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[11px] font-mono text-white/40">ROE</span>
                  <span className={`text-xs font-mono font-bold ${roeVal >= 0 ? "text-[#4ade80]" : "text-[#f87171]"}`}>{roeVal >= 0 ? "+" : ""}{roeVal}%</span>
                </div>
              )}
              {(mode === "pnl" || mode === "both") && (
                <div className="flex justify-between items-center py-1">
                  <span className="text-[11px] font-mono text-white/40">PnL</span>
                  <span className={`text-xs font-mono font-bold ${pnlVal >= 0 ? "text-[#4ade80]" : "text-[#f87171]"}`}>{pnlVal >= 0 ? "+" : ""}{pnlVal.toFixed(2)} USDT</span>
                </div>
              )}
            </div>

            <div className="border-t border-white/[0.06] pt-4 flex flex-col gap-2 text-[11px] font-mono">
              {[
                { label: "Entry", val: signal.entry, color: "text-white" },
                { label: "TP", val: signal.tp, color: "text-[#4ade80]" },
                { label: "SL", val: signal.sl, color: "text-[#f87171]" },
              ].map((row) => (
                <div key={row.label} className="flex justify-between text-white/40">
                  <span>{row.label}</span>
                  <span className={row.color}>{row.val != null && Number(row.val) > 0 ? `$${smartFmt(Number(row.val))}` : "—"}</span>
                </div>
              ))}
              {signal.pnl_pct != null && (
                <div className="flex justify-between text-white/40 pt-1 border-t border-white/[0.04]">
                  <span>Result</span>
                  <span className={signal.pnl_pct >= 0 ? "text-[#4ade80]" : "text-[#f87171]"}>{signal.result} · {signal.pnl_pct >= 0 ? "+" : ""}{signal.pnl_pct.toFixed(4)}%</span>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-2.5 pt-2 border-t border-white/[0.06]">
              <button onClick={handleSave} className="relative flex items-center justify-center gap-2 w-full py-3 rounded-xl text-xs font-mono font-bold tracking-wider bg-gradient-to-r from-[#d4a847] to-[#b8942e] text-black hover:brightness-110 hover:shadow-[0_0_20px_rgba(212,168,71,0.3)] transition-all active:scale-[0.98] overflow-hidden">
                {!hdReady && <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-[shimmer_1.2s_infinite]" style={{backgroundSize:'200% 100%'}} />}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                {hdReady ? "Save HD PNG" : "Preparing…"}
              </button>
              <button onClick={handleShare} disabled={sharing} className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-xs font-mono font-bold tracking-wider border border-[#d4a847]/30 text-[#d4a847] hover:bg-[#d4a847]/10 hover:border-[#d4a847]/50 hover:shadow-[0_0_20px_rgba(212,168,71,0.15)] transition-all disabled:opacity-40 active:scale-[0.98]">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>
                {sharing ? "Sharing…" : "Share"}
              </button>
              <p className="text-[9px] text-white/30 text-center font-mono leading-relaxed">Share via WhatsApp, Telegram, X, etc.</p>
            </div>
          </div>

          {/* Canvas Preview */}
          <div className="flex-1 p-4 sm:p-6 flex items-center justify-center bg-[#050508] relative overflow-hidden">
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-[300px] h-[300px] rounded-full bg-[#d4a847]/5 blur-[80px]" />
            </div>
            <canvas ref={canvasRef} className="relative z-10" style={{ borderRadius: 16, maxWidth: "100%", boxShadow: "0 20px 60px rgba(0,0,0,0.8), 0 0 0 1px rgba(212,168,71,0.08)" }} />
          </div>
        </div>
      </div>
    </div>
  , document.body);
}

export default function PosterButton({
  signal,
  leverage = 50,
  entryUsdt = 20,
  allowForClosed = false,
}: {
  signal: Signal;
  leverage?: number;
  entryUsdt?: number;
  allowForClosed?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const shouldShow =
    (signal.entry_hit && signal.status === "OPEN") ||
    (allowForClosed && (signal.status === "CLOSED" || signal.status === "INVALIDATED") && signal.result != null);
  if (!shouldShow) return null;

  return (
    <>
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(true); }}
        title="Share trade poster"
        className="inline-flex items-center justify-center w-7 h-7 rounded-lg border border-[#d4a847]/30 bg-[#d4a847]/5 text-[#d4a847] hover:bg-[#d4a847]/15 hover:border-[#d4a847]/60 hover:shadow-[0_0_12px_rgba(212,168,71,0.2)] transition-all duration-200"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </button>
      {open && (
        <PosterModal signal={signal} leverage={leverage} entryUsdt={entryUsdt} onClose={() => setOpen(false)} />
      )}
    </>
  );
}
