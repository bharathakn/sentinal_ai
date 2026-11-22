import { formatAmount } from "../../lib/format";
import { useCountUp } from "../../lib/motion";
import type { Screening } from "../../lib/run";

export function ScreeningScene({ s }: { s: Screening }) {
  const screened = useCountUp(s.screened, 420);
  const flagged = useCountUp(s.flagged, 420);
  const clear = s.histogram.map((n, i) => n - (s.flaggedHistogram[i] ?? 0));
  // Square-root scale: the few high-signal bars would vanish next to the normal ones otherwise.
  const max = Math.sqrt(Math.max(1, ...s.histogram));
  const rows = s.done ? s.selected : s.stream.slice(0, 8);
  return (
    <div className="screening">
      <div className="screen-main">
        <div className="counters">
          <div className="counter"><strong>{Math.round(screened).toLocaleString("en-IN")}</strong><span>of {s.total.toLocaleString("en-IN")} screened</span></div>
          <div className="counter counter-flag"><strong>{Math.round(flagged).toLocaleString("en-IN")}</strong><span>flagged as unusual</span></div>
        </div>
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={s.total} aria-valuenow={s.screened}>
          <i style={{ width: `${s.total ? (s.screened / s.total) * 100 : 0}%` }} />
        </div>
        <div className="histogram" aria-hidden="true">
          {(s.histogram.length ? s.histogram : Array<number>(24).fill(0)).map((n, i) => (
            <span key={i} className="col" style={{ height: `${(Math.sqrt(n) / max) * 100}%` }}>
              <i className="col-flag" style={{ flexGrow: s.flaggedHistogram[i] ?? 0 }} />
              <i className="col-clear" style={{ flexGrow: clear[i] ?? 0 }} />
            </span>
          ))}
        </div>
        <div className="axis"><span>Normal</span><span>Anomaly signal (bar height on a square-root scale)</span><span>Highly unusual</span></div>
        {s.done && s.flagged === 0 && <p className="note note-info">Nothing crossed either model's threshold.</p>}
      </div>
      <div className={`stream ${s.done ? "stream-done" : ""}`}>
        <h4>{s.done ? "Chosen for full investigation" : "Passing through the models"}</h4>
        <ul>
          {rows.map((t, i) => (
            <li key={`${s.done ? "sel" : "scan"}-${t.transaction_id}`} className={t.flagged ? "hit" : ""}
                style={s.done ? { animationDelay: `${i * 0.18}s` } : undefined}>
              <i className="tick" />
              <span className="stream-id">{t.transaction_id}<small>{formatAmount(t.amount, t.currency)} · {t.channel}</small></span>
              <b>{t.combined_confidence.toFixed(2)}</b>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
