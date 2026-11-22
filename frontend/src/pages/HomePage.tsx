import { useEffect, useRef, useState, type DragEvent } from "react";
import { Icon } from "../components/Icons";
import { ApiError, api } from "../lib/api";
import { relativeTime } from "../lib/format";
import { STAGES, type DemoInfo, type Run } from "../lib/run";
import { navigate } from "../lib/router";

const MAX_BYTES = 8 * 1024 * 1024; // the server enforces the same limit

export function fileProblem(file: { name: string; size: number }): string | null {
  if (/\.xlsx?$/i.test(file.name)) return "Excel files need saving as CSV first (File → Save as → CSV).";
  if (!/\.(csv|json)$/i.test(file.name)) return "Choose a CSV or JSON file.";
  if (file.size > MAX_BYTES) return "The file is larger than 8 MB.";
  return null;
}

export function HomePage() {
  const [demo, setDemo] = useState<DemoInfo | null>(null);
  const [recent, setRecent] = useState<Run[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [top, setTop] = useState(5);
  const [allowAi, setAllowAi] = useState(false);
  const [busy, setBusy] = useState<"demo" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Both are optional decoration: the page works without them.
    api.demoInfo().then(setDemo).catch(() => setDemo(null));
    api.listRuns().then((r) => setRecent(r.items)).catch(() => setRecent([]));
  }, []);

  function choose(f: File | undefined) {
    if (!f) return;
    const problem = fileProblem(f);
    setError(problem);
    setFile(problem ? null : f);
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    choose(e.dataTransfer.files[0]);
  }

  async function start(kind: "demo" | "upload") {
    setBusy(kind);
    setError(null);
    try {
      const run = kind === "demo" ? await api.startDemoRun(top, true) : await api.startUploadRun(file!, top, allowAi);
      navigate(`/runs/${run.run_id}`);
    } catch (e) {
      setError(e instanceof ApiError
        ? e.status === 429 ? "Other investigations are still running. Try again in a moment." : e.message
        : "The service is not reachable right now.");
      setBusy(null);
    }
  }

  return (
    <div className="home">
      <h1 className="headline">Detect it, trace it, explain it, resolve it.</h1>
      <p className="lede">
        Upload a transaction file. Five AI agents find what looks like fraud, gather the evidence, follow the money
        and hand you a checked report. The final decision is always yours.
      </p>

      <div className={`drop ${over ? "drop-over" : ""} ${file ? "drop-ready" : ""}`}
           onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}>
        <span className="drop-icon"><Icon name="file" size={26} /></span>
        <strong>{file ? file.name : "Drop your transaction file here"}</strong>
        <span className="drop-hint">
          {file ? `${(file.size / 1024).toLocaleString("en-IN", { maximumFractionDigits: 0 })} KB · ready to investigate`
            : "CSV or JSON · up to 10,000 transactions"}
        </span>
        <button className="btn" onClick={() => input.current?.click()}>{file ? "Choose another" : "Choose file"}</button>
        <input ref={input} type="file" accept=".csv,.json,text/csv,application/json" hidden aria-label="Transaction file"
               onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />
      </div>

      <div className="options">
        <label className="option">
          Fully investigate the
          <select value={top} onChange={(e) => setTop(Number(e.target.value))} aria-label="Transactions to investigate">
            {[1, 3, 5, 10].map((n) => <option key={n} value={n}>top {n}</option>)}
          </select>
          flagged transactions
        </label>
        <a className="pill pill-soft" href={api.sampleCsvUrl} download>Download a sample file</a>
      </div>

      {file && (
        <label className="check consent rise">
          <input type="checkbox" checked={allowAi} onChange={(e) => setAllowAi(e.target.checked)} />
          <span>
            Let Groq write the reports for this file. Case evidence is sent to Groq; leave this off and reports are
            written on the server. Use synthetic or anonymised data only.
          </span>
        </label>
      )}
      {error && <div className="note note-error" role="alert">{error}</div>}

      <div className="start">
        <button className="btn btn-primary btn-lg" disabled={!file || !!busy} onClick={() => start("upload")}>
          <Icon name="upload" size={17} />{busy === "upload" ? "Uploading…" : "Upload and investigate"}
        </button>
        <span className="muted">or</span>
        <button className="btn btn-lg" disabled={!!busy} onClick={() => start("demo")}>
          <Icon name="spark" size={17} />{busy === "demo" ? "Starting…" : "Load demo dataset"}
        </button>
      </div>

      <div className="demo-card">
        <span className="demo-icon"><Icon name="data" size={20} /></span>
        <div>
          <strong>Demo dataset</strong>
          <p>
            {demo
              ? `${demo.rows.toLocaleString("en-IN")} Indian transactions between ${demo.accounts.toLocaleString("en-IN")} accounts over ${demo.channels.join(", ")}`
              : "Indian bank transactions"}
            , with realistic fraud planted: layering chains, mule accounts, fraud rings, structuring and account takeovers.
            All of it is synthetic, and the agents never see the answers.
          </p>
        </div>
      </div>

      <ol className="five">
        {STAGES.map((s, i) => (
          <li key={s.name} style={{ animationDelay: `${0.15 + i * 0.1}s` }}>
            <div><span className="numeral">{i + 1}</span><strong>{s.name}</strong></div>
            <p>{s.blurb}</p>
          </li>
        ))}
      </ol>

      {recent.length > 0 && (
        <section className="recent">
          <h2>Recent investigations</h2>
          <ul>
            {recent.map((r) => (
              <li key={r.run_id}>
                <a href={`#/runs/${r.run_id}`}>
                  <strong>{r.dataset.name}</strong>
                  <span>{r.result ? `${r.result.investigated} investigated, ${r.result.flagged.toLocaleString("en-IN")} flagged`
                    : r.status === "FAILED" ? "Did not finish" : "Running"}</span>
                  <small>{relativeTime(r.created_at_utc)}</small>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
