import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

export type DropdownOption = { value: string; label: string; meta?: string; disabled?: boolean };

/** Octagon "puzzle" dropdown: the menu's pieces interlock as they open, with diamond
 * fillers where four corners meet. Keyboard: Enter/Space/ArrowDown open, Escape closes. */
export function Dropdown({
  label,
  value,
  options,
  onChange,
  trigger,
  className = "",
  style,
}: {
  label: string;
  value?: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  trigger?: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    root.current?.querySelector<HTMLElement>('.opt[aria-selected="true"], .opt:not([aria-disabled="true"])')?.focus();
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const pick = (o: DropdownOption) => {
    if (o.disabled) return;
    onChange(o.value);
    setOpen(false);
  };

  return (
    <div ref={root} className={`dd ${className}`} data-open={open ? "" : undefined} style={style}>
      <button
        type="button"
        className="dd-trigger ob"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => e.key === "ArrowDown" && (e.preventDefault(), setOpen(true))}
      >
        {trigger ?? (
          <span>
            <span className="muted small">{label} </span>
            <span>{current?.label ?? ""}</span>
          </span>
        )}
        <span className="chev" />
      </button>
      {open && (
        <ul className="dd-menu" role="listbox" aria-label={label}>
          {options.map((o, i) => (
            <li
              key={o.value}
              className="opt"
              role="option"
              tabIndex={o.disabled ? -1 : 0}
              aria-selected={o.value === value}
              aria-disabled={o.disabled || undefined}
              style={{ "--i": i } as CSSProperties}
              onClick={() => pick(o)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  pick(o);
                } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const items = [...(root.current?.querySelectorAll<HTMLElement>('.opt:not([aria-disabled="true"])') ?? [])];
                  const k = items.indexOf(e.currentTarget);
                  items[(k + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
                }
              }}
            >
              <span className="pc">
                <span className="ok-mark">✓</span>
                <span>{o.label}</span>
                <span className="m">{o.meta ?? ""}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
