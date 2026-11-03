import type { CSSProperties } from "react";
import logoPermian from "../assets/logo-permian.svg";
import logoBlueprint from "../assets/logo-blueprint.svg";
import logoGraphite from "../assets/logo-graphite.svg";

/** The Stomato mantis shrimp mark. Permian is the main logo; the active palette
 *  (html[data-palette]) picks its matching colourway in kit.css. */
export function Logo({ width = 40 }: { width?: number }) {
  return (
    <span className="mark" style={{ "--mw": `${width}px` } as CSSProperties} aria-hidden="true">
      <img className="permian" src={logoPermian} alt="" />
      <img className="blueprint" src={logoBlueprint} alt="" />
      <img className="graphite" src={logoGraphite} alt="" />
    </span>
  );
}
