export function Placeholder({ layer, what }: { layer: string; what: string }) {
  return (
    <p className="placeholder">
      {what} arrives in layer {layer}.
    </p>
  );
}
