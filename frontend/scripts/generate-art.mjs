// Generates public/art/fields.svg — an original aerial-farmland illustration used on the
// auth screens and dashboard headers. Deterministic (seeded) so the output is stable.
//   node scripts/generate-art.mjs
import { mkdirSync, writeFileSync } from "node:fs";

let seed = 20260927;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
const pick = (a) => a[Math.floor(rnd() * a.length)];
const r = (a, b) => a + rnd() * (b - a);

const W = 1600, H = 1000;
const COLS = 11, ROWS = 8;
const cw = 2400 / COLS, ch = 1800 / ROWS;

// Muted crop palette: paddy greens, millet olive, harvested stubble, ploughed soil, fallow.
const FIELDS = [
  ["#6f8f4e", "#5b7a3d"], ["#7f9b52", "#667f40"], ["#58773f", "#46612f"], ["#8aa35c", "#6f8747"],
  ["#a8a45e", "#8d8a4a"], ["#c2a867", "#a88f51"], ["#b8925a", "#9b7847"], ["#8c6f4f", "#735a3f"],
  ["#9fae6a", "#83914f"], ["#6a8551", "#556d40"],
];

// Shared jittered lattice so neighbouring fields meet exactly.
const pts = [];
for (let j = 0; j <= ROWS; j++) {
  pts.push([]);
  for (let i = 0; i <= COLS; i++) {
    pts[j].push([i * cw + (i % COLS ? r(-38, 38) : 0) - 400, j * ch + (j % ROWS ? r(-30, 30) : 0) - 400]);
  }
}

let defs = "", fields = "", bunds = "";
let pid = 0;
for (let j = 0; j < ROWS; j++) {
  for (let i = 0; i < COLS; i++) {
    const [a, b, c, d] = [pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i]];
    // Occasionally split a plot into two strips, like smallholdings.
    const plots = rnd() < 0.45
      ? (() => {
          const t = r(0.35, 0.65);
          const m1 = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
          const m2 = [d[0] + (c[0] - d[0]) * t, d[1] + (c[1] - d[1]) * t];
          return [[a, m1, m2, d], [m1, b, c, m2]];
        })()
      : [[a, b, c, d]];
    for (const poly of plots) {
      const [fill, row] = pick(FIELDS);
      const angle = (rnd() < 0.5 ? 0 : 90) + r(-8, 8);
      const gap = r(7, 13);
      const id = `p${pid++}`;
      defs += `<pattern id="${id}" width="${gap.toFixed(1)}" height="${gap.toFixed(1)}" patternUnits="userSpaceOnUse" patternTransform="rotate(${angle.toFixed(1)})"><rect width="100%" height="100%" fill="${fill}"/><rect width="${(gap * 0.38).toFixed(1)}" height="${gap.toFixed(1)}" fill="${row}" opacity="0.55"/></pattern>`;
      const dstr = "M" + poly.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("L") + "Z";
      fields += `<path d="${dstr}" fill="url(#${id})"/>`;
      bunds += `<path d="${dstr}"/>`;
    }
  }
}

// Tree lines along a few boundaries.
let trees = "";
for (let k = 0; k < 16; k++) {
  const j = Math.floor(r(1, ROWS)), i = Math.floor(r(0, COLS));
  const [p, q] = [pts[j][i], pts[j][i + 1]];
  const n = Math.floor(r(5, 11));
  for (let t = 0; t < n; t++) {
    const u = t / n + r(-0.02, 0.02);
    const x = p[0] + (q[0] - p[0]) * u, y = p[1] + (q[1] - p[1]) * u;
    const rad = r(7, 13);
    trees += `<circle cx="${x.toFixed(1)}" cy="${(y + 4).toFixed(1)}" r="${rad.toFixed(1)}" fill="#1f3a22" opacity="0.35"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${rad.toFixed(1)}" fill="#35592f"/>`;
  }
}

const road = `<path d="M-100,${H * 0.72} C ${W * 0.25},${H * 0.58} ${W * 0.45},${H * 0.95} ${W * 0.7},${H * 0.62} S ${W + 100},${H * 0.35} ${W + 200},${H * 0.4}" fill="none" stroke="#d9cfb2" stroke-width="16" stroke-linecap="round"/>`;
const canal = `<path d="M${W * 0.18},-50 C ${W * 0.3},${H * 0.3} ${W * 0.12},${H * 0.55} ${W * 0.28},${H + 60}" fill="none" stroke="#7fa3a0" stroke-width="9" opacity="0.85"/>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice"><defs>${defs}</defs><g transform="rotate(-14 ${W / 2} ${H / 2}) translate(-80 -60)">${fields}<g fill="none" stroke="#e3dcc2" stroke-width="3.5" opacity="0.7">${bunds}</g>${canal}${road}${trees}</g></svg>`;

mkdirSync(new URL("../public/art/", import.meta.url), { recursive: true });
writeFileSync(new URL("../public/art/fields.svg", import.meta.url), svg);
console.log(`fields.svg: ${(svg.length / 1024).toFixed(0)} KB, ${pid} plots`);
