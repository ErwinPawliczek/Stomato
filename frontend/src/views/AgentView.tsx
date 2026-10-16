import { useState } from "react";

type Call = [call: string, result: string];
type Msg = { who: "You" | "Agent"; text: string; calls?: Call[]; table?: [string, string][] };

// Sample conversation shown until the agent backend (B-08 / F-08) lands. Numbers are mockups.
const SAMPLE: Msg[] = [
  { who: "You", text: "What happens to compressor power if K-101 discharges higher? Sweep it up to 8,000 kPa absolute." },
  {
    who: "Agent",
    calls: [
      ['read_variable("K-101.power")', "✓ 1,505.8 kW"],
      ['case_study("K-101.P_out", 7000 → 8000 kPa, 5 points)', "✓ 5 solves"],
      ['render("chart")', "✓"],
    ],
    table: [
      ["P_out, kPa(a)", "Power, kW"],
      ["7,000", "1,506"],
      ["7,250", "1,586"],
      ["7,500", "1,665"],
      ["7,750", "1,741"],
      ["8,000", "1,816"],
    ],
    text: "Power rises steadily with discharge pressure, about 78 kW for every 250 kPa. The cooler duty on E-101 rises with it.",
  },
  { who: "You", text: "Add a scrubber ahead of K-101 and re-solve." },
  {
    who: "Agent",
    calls: [
      ['add_unit(kind="scrubber", tag="V-102")', "✓"],
      ['connect("V-101.gas_out", "V-102.inlet")', "✓"],
      ['connect("V-102.gas_out", "K-101.inlet")', "✓"],
      ["solve()", "✓ converged, 1 pass"],
    ],
    text: "V-102 is in the flowsheet and the model converged. Regenerate the drawings to put it on the P&ID and plot plan.",
  },
];

/** Chat with the engine agent: full-width conversation with a large composer. */
export function AgentView() {
  const [draft, setDraft] = useState("");
  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Agent</h1>
          <p>Ask for changes in plain language. The agent works through the same API as the screens, and every tool call is shown.</p>
        </div>
      </div>
      <section className="chat ob" aria-label="Conversation">
        {SAMPLE.map((m, i) => (
          <div key={i} className={"msg " + (m.who === "You" ? "user" : "bot")}>
            <span className="who">{m.who}</span>
            {m.calls && (
              <div className="calls">
                {m.calls.map(([c, r]) => (
                  <span key={c} className="call">
                    <span>{c}</span>
                    <span className="okc">{r}</span>
                  </span>
                ))}
              </div>
            )}
            {m.table && (
              <table className="mini-t">
                <thead>
                  <tr>
                    <th>{m.table[0][0]}</th>
                    <th>{m.table[0][1]}</th>
                  </tr>
                </thead>
                <tbody>
                  {m.table.slice(1).map(([a, b]) => (
                    <tr key={a}>
                      <td>{a}</td>
                      <td>{b}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <span>{m.text}</span>
          </div>
        ))}
        <form className="composer" onSubmit={(e) => e.preventDefault()}>
          <div className="inp ob">
            <textarea
              name="ask"
              aria-label="Message"
              placeholder="Ask about the flowsheet or request a change"
              rows={5}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          </div>
          <button type="submit" className="btn ob primary" disabled title="The agent backend is not connected yet">
            Send
          </button>
        </form>
        <p className="small muted note">Sample conversation with mockup numbers. Sending arrives with the agent backend.</p>
      </section>
    </section>
  );
}
