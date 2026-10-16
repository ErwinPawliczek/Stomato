import type { CSSProperties, ReactNode } from "react";
import { Logo } from "./Logo";
import { PALETTES, type PaletteId } from "../theme/palettes";

export type GlobalPage = "home" | "equipment" | "sheet" | "agent";

const ICONS: Record<GlobalPage, ReactNode> = {
  home: (
    <>
      <path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" />
      <path d="M9 15v-4l3-2 3 2v4z" />
    </>
  ),
  equipment: (
    <>
      <rect x="7" y="2.5" width="10" height="19" rx="5" />
      <path d="M7 9h10M7 15h10" />
    </>
  ),
  sheet: (
    <>
      <path d="M3 4h18v16H3z" />
      <path d="M3 9h18M3 14h18M8 4v16M14 4v16" />
    </>
  ),
  agent: (
    <>
      <path d="M7 4h10l4 4v6l-4 4h-6l-5 3v-3l-3-3V8z" />
      <path d="M8.5 11h.01M12 11h.01M15.5 11h.01" strokeWidth="2.6" strokeLinecap="round" />
    </>
  ),
};

export const NAV: { id: GlobalPage; label: string }[] = [
  { id: "home", label: "Home" },
  { id: "equipment", label: "Equipment" },
  { id: "sheet", label: "Sheet" },
  { id: "agent", label: "Agent" },
];

/** Left rail: the logo (the only place the name "Stomato" appears), the global pages,
 * and the palette switch. */
export function Rail({
  current,
  onNavigate,
  palette,
  onPalette,
}: {
  current: GlobalPage;
  onNavigate: (p: GlobalPage) => void;
  palette: PaletteId;
  onPalette: (p: PaletteId) => void;
}) {
  return (
    <nav className="rail ob" aria-label="Main">
      <button type="button" className="brandlink" onClick={() => onNavigate("home")} aria-label="Stomato home">
        <Logo width={54} />
        <span className="brandword">Stomato</span>
      </button>
      {NAV.map((n) => (
        <button
          key={n.id}
          type="button"
          className="navb"
          aria-current={current === n.id ? "page" : undefined}
          onClick={() => onNavigate(n.id)}
        >
          <span className="ic">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {ICONS[n.id]}
            </svg>
          </span>
          {n.label}
        </button>
      ))}
      <span className="spacer" />
      <div className="pal" role="group" aria-label="Palette">
        <span className="lbl">Palette</span>
        {(Object.keys(PALETTES) as PaletteId[]).map((id) => (
          <button
            key={id}
            type="button"
            className="palb ob"
            aria-pressed={palette === id}
            aria-label={`${PALETTES[id].name} palette`}
            title={PALETTES[id].name}
            style={{ "--obFill": PALETTES[id].accent === "#FFFFFF" ? PALETTES[id].bg : PALETTES[id].accent } as CSSProperties}
            onClick={() => onPalette(id)}
          />
        ))}
      </div>
    </nav>
  );
}
