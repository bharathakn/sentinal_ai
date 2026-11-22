import { useState, type FormEvent } from "react";
import { Icon, Logo, STAGE_ICONS } from "../components/Icons";
import { ApiError, api } from "../lib/api";
import { STAGES } from "../lib/run";
import type { User } from "../lib/types";

export function LoginPage({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await api.login(username, password, remember));
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        const mins = err.retryAfter ? Math.ceil(err.retryAfter / 60) : 15;
        setError(`Too many failed attempts. Try again in about ${mins} minute${mins === 1 ? "" : "s"}.`);
      } else if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect username or password.");
      } else {
        setError("The service is not reachable right now. If it was idle, it may take up to a minute to wake up.");
      }
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-story">
        <div className="brand brand-lg"><Logo /><span>Sentinel AI</span></div>
        <p className="headline">Detect it, trace it, explain it, resolve it.</p>
        <ol className="login-stages">
          {STAGES.map((s, i) => (
            <li key={s.name} style={{ animationDelay: `${i * 1.1}s` }}><Icon name={STAGE_ICONS[i]} /><span>{s.name}</span></li>
          ))}
        </ol>
      </div>
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <h1 id="login-title">Analyst sign-in</h1>
        <label>
          Username
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label>
          Password
          <input type="password" autoComplete="current-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Keep me signed in on this device
        </label>
        {error && <div className="note note-error" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="fineprint">
          Prototype for demonstration. Synthetic data and mock banking services only. Accounts are issued by an
          administrator.
        </p>
      </form>
    </div>
  );
}
