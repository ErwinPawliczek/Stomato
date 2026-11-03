import { api, TAB_ACTOR, type Change } from "./client";
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

/** Follow the open project's live change stream: every change from another
 * actor (another tab, the in-app agent, the MCP server, a REST script) raises the
 * project-changed signal; `onChange` also receives it. This tab's own edits
 * (actor TAB_ACTOR) are skipped — the view that made them already re-rendered
 * from the response. The server starts the stream at the latest change, so no
 * backlog replays. Returns an unsubscribe. */
export function followProjectChanges(onChange?: (c: Change) => void): () => void {
  return api.history.subscribe((c) => {
    if (c.actor === TAB_ACTOR) return;
    onChange?.(c);
    notifyProjectChanged();
  });
}
