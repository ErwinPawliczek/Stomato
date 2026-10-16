import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

/** A scroll area inside an octagon frame, with octagon thumbs drawn in their own gutter
 * instead of the browser's scroll bars. Thumbs drag; clicking the gutter pages. */
export function OctScroll({
  children,
  label,
  maxHeight,
  className = "",
}: {
  children: ReactNode;
  label: string;
  maxHeight?: string;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const sc = useRef<HTMLDivElement>(null);
  const vb = useRef<HTMLDivElement>(null);
  const hb = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const b = box.current!, s = sc.current!, v = vb.current!, h = hb.current!;
    const vt = v.firstElementChild as HTMLElement, ht = h.firstElementChild as HTMLElement;
    const upd = () => {
      const H = s.scrollHeight, ch = s.clientHeight, W = s.scrollWidth, cw = s.clientWidth;
      v.hidden = H <= ch + 1;
      h.hidden = W <= cw + 1;
      b.toggleAttribute("data-nov", v.hidden);
      b.toggleAttribute("data-noh", h.hidden);
      if (!v.hidden) {
        const L = v.clientHeight, th = Math.max(34, (L * ch) / H);
        vt.style.height = th + "px";
        vt.style.transform = `translateY(${((L - th) * s.scrollTop) / (H - ch)}px)`;
      }
      if (!h.hidden) {
        const L = h.clientWidth, tw = Math.max(34, (L * cw) / W);
        ht.style.width = tw + "px";
        ht.style.transform = `translateX(${((L - tw) * s.scrollLeft) / (W - cw)}px)`;
      }
    };
    const drag = (thumb: HTMLElement, y: boolean) => (e: PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      thumb.setPointerCapture?.(e.pointerId);
      b.setAttribute("data-drag", "");
      const start = y ? e.clientY : e.clientX, s0 = y ? s.scrollTop : s.scrollLeft;
      const range = y
        ? (s.scrollHeight - s.clientHeight) / (v.clientHeight - thumb.offsetHeight)
        : (s.scrollWidth - s.clientWidth) / (h.clientWidth - thumb.offsetWidth);
      const move = (ev: PointerEvent) => {
        const d = ((y ? ev.clientY : ev.clientX) - start) * range;
        if (y) s.scrollTop = s0 + d;
        else s.scrollLeft = s0 + d;
      };
      const up = () => {
        b.removeAttribute("data-drag");
        thumb.removeEventListener("pointermove", move);
        thumb.removeEventListener("pointerup", up);
        thumb.removeEventListener("pointercancel", up);
      };
      thumb.addEventListener("pointermove", move);
      thumb.addEventListener("pointerup", up);
      thumb.addEventListener("pointercancel", up);
    };
    const page = (y: boolean) => (e: PointerEvent) => {
      const bar = y ? v : h, t = y ? vt : ht;
      if (e.target !== bar) return;
      const r = t.getBoundingClientRect();
      const dir = (y ? e.clientY < r.top : e.clientX < r.left) ? -1 : 1;
      s.scrollBy(y ? { top: dir * s.clientHeight * 0.9, behavior: "smooth" } : { left: dir * s.clientWidth * 0.9, behavior: "smooth" });
    };
    const dv = drag(vt, true), dh = drag(ht, false), pv = page(true), ph = page(false);
    vt.addEventListener("pointerdown", dv);
    ht.addEventListener("pointerdown", dh);
    v.addEventListener("pointerdown", pv);
    h.addEventListener("pointerdown", ph);
    s.addEventListener("scroll", upd, { passive: true });
    window.addEventListener("resize", upd);
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(upd);
      ro.observe(s);
      if (s.firstElementChild) ro.observe(s.firstElementChild);
    }
    upd();
    return () => {
      vt.removeEventListener("pointerdown", dv);
      ht.removeEventListener("pointerdown", dh);
      v.removeEventListener("pointerdown", pv);
      h.removeEventListener("pointerdown", ph);
      s.removeEventListener("scroll", upd);
      window.removeEventListener("resize", upd);
      ro?.disconnect();
    };
  }, []);

  return (
    <div ref={box} className={`scrollbox ob ${className}`} style={maxHeight ? ({ "--sh": maxHeight } as CSSProperties) : undefined}>
      <div ref={sc} className="scroll" tabIndex={0} aria-label={label}>
        {children}
      </div>
      <div ref={vb} className="vbar" aria-hidden="true">
        <i />
      </div>
      <div ref={hb} className="hbar" aria-hidden="true">
        <i />
      </div>
    </div>
  );
}
