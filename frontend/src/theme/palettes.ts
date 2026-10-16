// Stomato palettes. Each palette is a small set of base colours; tokens() expands it
// into the CSS custom properties the octagon kit (theme/kit.css) reads.
export type Palette = {
  name: string;
  mode: "Light" | "Dark";
  bg: string;
  surface: string;
  surface2: string;
  ink: string;
  muted: string;
  line: string;
  inLine: string;
  accent: string;
  accent2: string;
  accent3: string;
  onAccent: string;
  accentText: string;
  ok: string;
  warn: string;
  bad: string;
  logoA: string;
  logoB: string;
  tagFill: string;
  shadow?: string;
};

export const PALETTES = {
  permian: {
    name: "Permian", mode: "Light", bg: "#F1ECE4", surface: "#FFFDF9", surface2: "#E8DFD2", ink: "#2A2622",
    muted: "#6E655B", line: "#D3C7B6", inLine: "#8C7F6E", accent: "#B5532A", accent2: "#33414D", accent3: "#7A8B5C",
    onAccent: "#FFFFFF", accentText: "#9C4421", ok: "#5E7D3A", warn: "#C98A12", bad: "#B23A2A",
    logoA: "#B5532A", logoB: "#33414D", tagFill: "#E8DFD2",
  },
  blueprint: {
    name: "Blueprint", mode: "Dark", bg: "#0F3D6E", surface: "#134A82", surface2: "#1A5794", ink: "#EAF3FF",
    muted: "#A9C6E8", line: "#3B72AD", inLine: "#8DB6E3", accent: "#FFFFFF", accent2: "#7FD3FF", accent3: "#FFD166",
    onAccent: "#0F3D6E", accentText: "#FFD166", ok: "#8BE0B0", warn: "#FFD166", bad: "#FF8A80",
    logoA: "#7FD3FF", logoB: "#FFFFFF", tagFill: "#0F3D6E", shadow: "#082746",
  },
  graphite: {
    name: "Mint Graphite", mode: "Light", bg: "#EEF2F0", surface: "#FFFFFF", surface2: "#E1EAE6", ink: "#1E2326",
    muted: "#5F6B70", line: "#CBD5D1", inLine: "#1E2326", accent: "#1E2326", accent2: "#2BC4A0", accent3: "#2BC4A0",
    onAccent: "#FFFFFF", accentText: "#138A6F", ok: "#1E9E7E", warn: "#D99A1E", bad: "#D9483B",
    logoA: "#2BC4A0", logoB: "#1E2326", tagFill: "#E1EAE6",
  },
} satisfies Record<string, Palette>;

export type PaletteId = keyof typeof PALETTES;
export const DEFAULT_PALETTE: PaletteId = "permian";
const STORE_KEY = "stomato.palette";

export function tokens(p: Palette): Record<string, string> {
  return {
    "--bg": p.bg, "--surface": p.surface, "--surface2": p.surface2, "--ink": p.ink, "--muted": p.muted,
    "--line": p.line, "--inLine": p.inLine, "--accent": p.accent, "--accent2": p.accent2, "--accent3": p.accent3,
    "--onAccent": p.onAccent, "--accentText": p.accentText, "--primaryBg": p.accent, "--btnLine": p.ink,
    "--ok": p.ok, "--warn": p.warn, "--bad": p.bad, "--focus": p.accent2, "--logoA": p.logoA, "--logoB": p.logoB,
    "--svgInk": p.ink, "--eqFill": p.surface, "--tagFill": p.tagFill, "--tagInk": p.ink,
    "--pieceBg": `color-mix(in srgb, ${p.accent2} 9%, ${p.surface})`, "--thumb": p.accent, "--thumbHot": p.accent2,
    "--rail": `color-mix(in srgb, ${p.ink} 11%, ${p.surface})`, "--shadowInk": p.shadow ?? p.ink,
    // backend drawings are drawn in black, so on a dark palette they sit on light paper
    "--paper": p.mode === "Dark" ? "#EAF3FF" : p.surface2,
  };
}

/** Writes the palette's tokens onto <html> and sets color-scheme to match. */
export function applyPalette(id: PaletteId, root: HTMLElement = document.documentElement): void {
  const p = PALETTES[id];
  for (const [k, v] of Object.entries(tokens(p))) root.style.setProperty(k, v);
  root.style.colorScheme = p.mode === "Dark" ? "dark" : "light";
  root.dataset.palette = id;
}

export function loadPalette(): PaletteId {
  try {
    const v = localStorage.getItem(STORE_KEY);
    if (v && v in PALETTES) return v as PaletteId;
  } catch {
    // storage blocked (private window): fall back to the default
  }
  return DEFAULT_PALETTE;
}

export function savePalette(id: PaletteId): void {
  try {
    localStorage.setItem(STORE_KEY, id);
  } catch {
    // not persisted; the choice still applies for this visit
  }
}
