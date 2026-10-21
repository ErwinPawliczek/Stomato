// One shared signal for "the project changed": the Agent view raises it after a
// `project_changed` event, and App.tsx subscribes to re-fetch every data-backed
// tab (Flowsheet via the project state, Results/Drawings via a remount key).
type Listener = () => void;

const listeners = new Set<Listener>();

/** Subscribe to project changes; returns an unsubscribe function. */
export function onProjectChanged(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Raise the signal — every subscriber re-fetches. */
export function notifyProjectChanged(): void {
  for (const fn of listeners) fn();
}
