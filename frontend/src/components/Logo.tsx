import type { CSSProperties } from "react";
import logoA from "../assets/logo-a.png";
import logoB from "../assets/logo-b.png";

/** The Stomato mark: two masked halves, each tinted from the active palette. */
export function Logo({ width = 40 }: { width?: number }) {
  return (
    <span className="mark" style={{ "--mw": `${width}px` } as CSSProperties} aria-hidden="true">
      <i className="a" style={{ "--m": `url(${logoA})` } as CSSProperties} />
      <i className="b" style={{ "--m": `url(${logoB})` } as CSSProperties} />
    </span>
  );
}
