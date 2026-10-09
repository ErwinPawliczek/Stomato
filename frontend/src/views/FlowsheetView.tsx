import type { Project } from "../api/client";

/** Layer 1: read-only list of units and streams. */
export function FlowsheetView({ project }: { project: Project }) {
  const fs = project.flowsheet;
  return (
    <div className="grid">
      <section>
        <h2>Units</h2>
        <table>
          <thead>
            <tr><th>Tag</th><th>Kind</th><th>Params</th></tr>
          </thead>
          <tbody>
            {fs.units.map((u) => (
              <tr key={u.tag} data-tag={u.tag}>
                <td>{u.tag}</td>
                <td>{u.kind}</td>
                <td><code>{JSON.stringify(u.params ?? {})}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Streams</h2>
        <table>
          <thead>
            <tr><th>ID</th><th>From</th><th>To</th><th>Service</th></tr>
          </thead>
          <tbody>
            {fs.streams.map((s) => (
              <tr key={s.id} data-stream={s.id}>
                <td>{s.id}</td>
                <td>{s.source ? `${s.source.unit}.${s.source.port}` : "feed"}</td>
                <td>{s.target ? `${s.target.unit}.${s.target.port}` : "product"}</td>
                <td>{s.service}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
