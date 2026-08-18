import { useCallback, useEffect, useState } from "react";

const demoAlert = {
  service: "orders-api",
  symptom: "pods restarting repeatedly, back-off restarting failed container",
  meta: { environment: "production-k8s" },
};

// The clickable demo card is handled separately; these are memory-display only.
const knowledge = [
  [
    "OOMKilled",
    "Pods killed for exceeding their memory limit",
    "increase container memory limit",
  ],
  [
    "ImagePullBackOff",
    "Pods cannot pull their container image",
    "publish or correct the image reference",
  ],
  [
    "OAuthRedirectMismatch",
    "SSO login fails with redirect_uri_mismatch",
    "register the exact production redirect URI",
  ],
  [
    "DBConnectionPoolExhaustion",
    "Requests time out, database pool exhausted",
    "increase pool capacity within database limits",
  ],
];

const labels = {
  triage: "Classifying the alert",
  memory_search: "Searching incident memory",
  reason: "Scoring past fixes",
  recommend: "Preparing recommendation",
  escalate: "No confident match",
};

const PIPELINE = ["triage", "memory_search", "reason", "recommend"];

const tone = (v) => (v >= 0.75 ? "high" : v >= 0.5 ? "medium" : "low");

const short = (v) => {
  const s = String(v || "").replace(/\s+/g, " ");
  return s.length > 120 ? `${s.slice(0, 119)}…` : s;
};

function Evidence({ evidence, card }) {
  const calls = Array.isArray(evidence?.tool_calls_made)
    ? evidence.tool_calls_made
    : [];

  const rows = calls.map((call, i) => {
    const [tool, args] = Array.isArray(call)
      ? call
      : [call?.name || call?.tool, call?.arguments || call];
    return [
      tool || "tool",
      short(
        args?.query ||
          args?.statement ||
          args?.table ||
          args?.database ||
          "CockroachDB"
      ),
      i,
    ];
  });

  if (!rows.length && evidence?.tool) {
    rows.push([evidence.tool, "fix history for this signature", 0]);
  }

  const results = Array.isArray(evidence?.raw_results)
    ? evidence.raw_results
    : [];
  const count = results.reduce(
    (n, r) => n + (Array.isArray(r?.rows) ? r.rows.length : 0),
    0
  );

  return (
    <>
      <section className="evidence-strip">
        <p className="eyebrow">Queried CockroachDB</p>
        {rows.length ? (
          rows.map(([t, q, i]) => (
            <div className="query-row mono" key={i}>
              <span>{t}</span>
              <span>{q}</span>
            </div>
          ))
        ) : (
          <p>Queried incident memory in CockroachDB.</p>
        )}
        {Array.isArray(evidence?.recent_attempts) && (
          <p className="mono">
            {evidence.recent_attempts.length} recent attempts found
          </p>
        )}
      </section>
      <div className="evidence-details">
        <details>
          <summary>What the agent found</summary>
          <p>
            {card?.match_summary || "Queried incident memory in CockroachDB."}
          </p>
          {results.length > 0 && (
            <p>
              Queried {results.length} tables, returned {count} rows.
            </p>
          )}
        </details>
      </div>
    </>
  );
}

function Result({
  card,
  outcome,
  id,
  approve,
  approving,
  approved,
  response,
}) {
  if (outcome === "ESCALATED") {
    return (
      <article className="escalation-card">
        <span className="history-status low">LOW</span>
        <h2>No confident recommendation</h2>
        <p>
          The agent has no confident history for this signature, so it escalated
          instead of inventing a fix.
        </p>
        <Evidence evidence={card?.live_evidence} card={card} />
      </article>
    );
  }

  const chosen = card.candidates.find((c) => c.action === card.chosen_action);
  const result = response?.execution_result;
  const stats = response?.stats;

  return (
    <article className="recommendation-card">
      <div className="card-heading">
        <h2>{card.signature}</h2>
        <span
          className={`history-status ${String(
            card.confidence_band
          ).toLowerCase()}`}
        >
          {card.confidence_band}
        </span>
      </div>
      {[...card.candidates]
        .sort(
          (a, b) =>
            (b.action === card.chosen_action) -
              (a.action === card.chosen_action) ||
            b.confidence - a.confidence
        )
        .map((c) => (
          <div className={`candidate-row ${tone(c.confidence)}`} key={c.action}>
            <span>
              {c.action}
              {c.action === card.chosen_action && " · chosen"}
            </span>
            <div className="confidence-track">
              <i
                className="confidence-fill"
                style={{ width: `${c.confidence * 100}%` }}
              />
            </div>
            <span className="mono">
              {Math.round(c.confidence * 100)}% {c.success_count}/
              {c.success_count + c.fail_count}
            </span>
          </div>
        ))}
      <p>
        Chose {card.chosen_action},{" "}
        <span className="mono">
          {chosen?.success_count || 0}/
          {(chosen?.success_count || 0) + (chosen?.fail_count || 0)}
        </span>{" "}
        past attempts succeeded, the strongest record.
      </p>
      <Evidence evidence={card.live_evidence} card={card} />
      <div className="evidence-details">
        <details>
          <summary>Why this action</summary>
          <p>
            {String(card.explanation || "")
              .replace(/\*\*/g, "")
              .replace(/\|/g, " ")}
          </p>
        </details>
      </div>
      <div className="live-actions">
        {!approved ? (
          <>
            <button
              className="primary-button"
              disabled={approving || !id}
              onClick={approve}
            >
              {approving ? "Applying rollback..." : "Approve fix"}
            </button>
            <small>A human approves before anything runs.</small>
          </>
        ) : (
          <button className="primary-button" disabled>
            Approved
          </button>
        )}
      </div>
      {response && result?.status === "executed" && result?.result === "success" && (
        <div className="execution-result">
          <strong>Rollback applied. orders-api healed.</strong>
          <p className="mono">
            {result.rollback_response?.body?.rolled_back_to || "v2.8.0"}, pool{" "}
            {result.rollback_response?.body?.pool_size || 20}
          </p>
        </div>
      )}
      {response && result?.status === "not_executable" && (
        <div className="execution-note">
          This action has no automated runbook in the demo sandbox. In production it
          would be executed by the matching runbook. The live heal demo runs the
          rollback path (CrashLoopBackOff).
        </div>
      )}
      {response && result?.status === "not_executable" && stats && (
        <p className="current-history">
          Current history for this action: <span className="mono">
            {stats.success_count}/{stats.success_count + stats.fail_count}
          </span>
        </p>
      )}
      {response && result?.status === "execution_error" && (
        <div className="execution-note">
          The action could not be executed: {result.error}.
        </div>
      )}
      {response && result?.status !== "not_executable" && result?.status !== "execution_error" && result?.result !== "success" && (
        <div className="execution-note">Action was not executed.</div>
      )}
      {stats && result?.status === "executed" && result?.result === "success" && (
        <p className="memory-updated">
          Recorded this outcome. {card.chosen_action} now{" "}
          <span className="mono">
            {stats.success_count}/{stats.success_count + stats.fail_count}
          </span>{" "}
          for {card.signature}.
        </p>
      )}
    </article>
  );
}

function StageDetail({ stage, card }) {
  if (stage === "triage") {
    return (
      <>
        Signature: <span className="mono">{card.signature}</span>
      </>
    );
  }
  if (stage === "memory_search") {
    return card.match_summary;
  }
  if (stage === "reason") {
    if (!card.candidates?.length) return "No confident candidates.";
    return card.candidates
      .map((c) => `${c.action} ${Math.round(c.confidence * 100)}%`)
      .join(", ");
  }
  if (stage === "recommend") {
    return <>Chose: {card.chosen_action}</>;
  }
  return "No additional detail.";
}

export default function App() {
  const [view, setView] = useState("incidents");
  const [sandbox, setSandbox] = useState({});
  const [alert, setAlert] = useState(null);
  const [stages, setStages] = useState([]);
  const [id, setId] = useState("");
  const [card, setCard] = useState(null);
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resetNote, setResetNote] = useState("");
  const [resetting, setResetting] = useState(false);
  const [approved, setApproved] = useState(false);
  const [approving, setApproving] = useState(false);
  const [response, setResponse] = useState(null);
  const [form, setForm] = useState({
    service: "",
    symptom: "",
    environment: "production-k8s",
  });

  const poll = useCallback(async () => {
    const probes = await Promise.allSettled([
      fetch("/sandbox/health"),
      fetch("/sandbox/health"),
    ]);
    let version = "";
    let down = false;

    for (const probe of probes) {
      if (probe.status !== "fulfilled") {
        down = true;
        continue;
      }
      try {
        const body = await probe.value.json();
        if (!version && body.version) version = body.version;
        if (!probe.value.ok || body.status !== "healthy") down = true;
      } catch {
        down = true;
      }
    }

    setSandbox({
      version,
      status: down ? "unhealthy" : "healthy",
      down,
    });
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [poll]);

  const reset = async () => {
    setResetNote("");
    const r = await fetch("/reset", { method: "POST" });
    const b = await r.json();
    if (!r.ok) throw Error(b.detail);
    await poll();
    setResetNote("orders-api rolled back to v2.8.1, broken state.");
    return b.sandbox;
  };

  const run = async (a) => {
    setAlert(a);
    setView("live");
    setBusy(true);
    setStages([]);
    setCard(null);
    setOutcome("");
    setId("");
    setApproved(false);
    setResponse(null);
    setMessage("");
    try {
      const r = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert: a }),
      });
      const rd = r.body.getReader();
      const d = new TextDecoder();
      let b = "";
      while (true) {
        const x = await rd.read();
        b += d.decode(x.value || new Uint8Array(), { stream: !x.done });
        let n = b.indexOf("\n\n");
        while (n >= 0) {
          const f = b.slice(0, n);
          b = b.slice(n + 2);
          const e = f.match(/event:\s*(.+)/)?.[1];
          const raw = f.match(/data:\s*(.+)/)?.[1];
          if (e && raw) {
            const v = JSON.parse(raw);
            if (e === "stage" && v.node !== "__interrupt__") {
              setId(v.thread_id);
              setStages((s) => (s.includes(v.node) ? s : [...s, v.node]));
            }
            if (e === "result") {
              setId(v.thread_id);
              setCard(v.card);
              setOutcome(v.outcome);
            }
            if (e === "error") {
              setMessage(`The run could not complete: ${v.message}`);
            }
          }
          n = b.indexOf("\n\n");
        }
        if (x.done) break;
      }
    } catch (e) {
      setMessage(`The run could not complete: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    setApproving(true);
    try {
      const r = await fetch("/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: id }),
      });
      const b = await r.json();
      if (!r.ok) throw Error(b.detail);
      setResponse(b);
      setApproved(true);
      poll();
    } catch (e) {
      setMessage(`The fix could not be applied: ${e.message}`);
    } finally {
      setApproving(false);
    }
  };

  const runReset = async () => {
    setResetting(true);
    try {
      await reset();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setResetting(false);
    }
  };

  const activeStage = busy
    ? PIPELINE.find((stage) => !stages.includes(stage))
    : undefined;

  return (
    <>
      <header className="app-header">
        <div className="brand">
          <i className="brand-mark" />
          RecallOps
        </div>
        <div className="app-header-actions">
          <nav className="app-nav">
            <button
              className={`nav-link ${view === "incidents" ? "is-active" : ""}`}
              onClick={() => setView("incidents")}
            >
              Incidents
            </button>
            <button
              className={`nav-link ${view === "live" ? "is-active" : ""}`}
              disabled={!alert}
              onClick={() => setView("live")}
            >
              Live analysis
            </button>
          </nav>
          <div className="sandbox-pill">
            <i className={`status-dot ${sandbox.down ? "is-failed" : "is-done"}`} />
            <span>
              orders-api <b className="mono">{sandbox.version || ""}</b>{" "}
              {sandbox.down ? "down" : "healthy"}
            </span>
          </div>
        </div>
      </header>
      <main className="app-shell">
        <section className="screen" hidden={view !== "incidents"}>
          <div className="screen-heading">
            <p className="eyebrow">Try an incident</p>
            <h1>Choose an incident to investigate.</h1>
            <p className="muted-copy">
              Run the live demo, describe your own, or see what else the agent has
              in memory.
            </p>
          </div>

          <div className="submission-card">
            {/* Primary money moment: the live demo card, first and prominent. */}
            <article className="knowledge-card is-live demo-card">
              <strong>CrashLoopBackOff</strong>
              <p>Pods restart repeatedly after a bad deploy or missing config</p>
              <button
                className="primary-button"
                disabled={busy}
                onClick={() => run(demoAlert)}
              >
                Run live demo
              </button>
            </article>

            <div className="reset-row">
              <button
                className="secondary-button"
                disabled={resetting}
                onClick={runReset}
              >
                {resetting ? "Resetting..." : "Reset sandbox"}
              </button>
              <p className="muted-copy">
                Resets orders-api to the broken state so you can watch the agent's
                fix take effect. Click this before running the live demo.
              </p>
            </div>
            {resetNote && <p className="reset-note mono">{resetNote}</p>}

            <div className="section-divider" />

            {/* Custom incident form. */}
            <div className="field-grid">
              <label className="field">
                <span>Service</span>
                <input
                  value={form.service}
                  onChange={(e) => setForm({ ...form, service: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Environment</span>
                <input
                  value={form.environment}
                  onChange={(e) =>
                    setForm({ ...form, environment: e.target.value })
                  }
                />
              </label>
              <label className="field field-wide">
                <span>Symptom</span>
                <textarea
                  value={form.symptom}
                  onChange={(e) => setForm({ ...form, symptom: e.target.value })}
                />
              </label>
            </div>
            <div className="form-footer">
              <button
                className="primary-button"
                disabled={busy || !form.service || !form.symptom}
                onClick={() =>
                  run({
                    service: form.service,
                    symptom: form.symptom,
                    meta: { environment: form.environment },
                  })
                }
              >
                Run investigation
              </button>
            </div>
            <p className="muted-copy custom-form-note">
              The CrashLoopBackOff card above runs the full heal. Copy any
              incident below into the form to see the agent's recommendation.
            </p>
            {message && <p className="inline-error">{message}</p>}

            <div className="section-divider" />

            {/* Memory breadth: other seeded signatures, display only. */}
            <p className="eyebrow">Also in memory</p>
            <div className="knowledge-grid">
              {knowledge.map(([signature, symptom]) => (
                <article className="knowledge-card" key={signature}>
                  <strong>{signature}</strong>
                  <div className="knowledge-row">
                    <span className="knowledge-label">Service</span>
                    <span className="knowledge-value">orders-api</span>
                  </div>
                  <div className="knowledge-row">
                    <span className="knowledge-label">Symptom</span>
                    <span className="knowledge-value">{symptom}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="screen" hidden={view !== "live"}>
          <button className="back-button" onClick={() => setView("incidents")}>
            ‹ Back to incidents
          </button>
          <div className="live-header">
            <div>
              <p className="eyebrow">Live analysis</p>
              <h1>Investigating your alert</h1>
              <div className="run-summary">
                <div>
                  <span>Service</span>
                  <strong className="mono">{alert?.service}</strong>
                </div>
                <div>
                  <span>Symptom</span>
                  <strong>{alert?.symptom}</strong>
                </div>
                <div>
                  <span>Environment</span>
                  <strong className="mono">{alert?.meta?.environment}</strong>
                </div>
              </div>
            </div>
          </div>
          <div className="live-proof-card">
            <div className="live-status-line">
              <i
                className={`status-dot ${
                  busy
                    ? "is-running"
                    : outcome === "ESCALATED"
                    ? "is-failed"
                    : "is-done"
                }`}
              />
              <p>{busy ? labels[activeStage] : "Analysis complete"}</p>
            </div>
            <ol className="stage-list">
              {PIPELINE.map((s) => {
                const complete = stages.includes(s);
                const active = busy && s === activeStage;
                return (
                  <li
                    className={`stage ${complete ? "is-complete" : active ? "is-active" : ""}`}
                    key={s}
                  >
                    <div className="stage-row">
                      <i className="stage-marker" />
                      <strong>{labels[s] || s}</strong>
                      <small>{complete ? "Complete" : active ? "Running" : "Waiting"}</small>
                    </div>
                    {complete && !busy && card && (
                      <details className="stage-expander">
                        <summary>Details</summary>
                        <div className="stage-detail">
                          <StageDetail stage={s} card={card} />
                        </div>
                      </details>
                    )}
                  </li>
                );
              })}
            </ol>
            {message && <p className="inline-error">{message}</p>}
            {card && (
              <Result
                card={card}
                outcome={outcome}
                id={id}
                approve={approve}
                approving={approving}
                approved={approved}
                response={response}
              />
            )}
          </div>
        </section>
      </main>
    </>
  );
}
