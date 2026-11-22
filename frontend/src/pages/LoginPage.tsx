import { useState, type FormEvent } from "react";
import { Icon, Logo, STAGE_ICONS } from "../components/Icons";
import { hasAccountHere, rememberAccount } from "../lib/account";
import { ApiError, api } from "../lib/api";
import { STAGES } from "../lib/run";
import type { User } from "../lib/types";

type Mode = "signup" | "signin";

const UNREACHABLE = "The service is not reachable right now. If it was idle, it may take up to a minute to wake up.";
const MIN_PASSWORD = 10; // the server enforces the same rule

export function signupProblem(username: string, password: string, confirm: string): string | null {
  if (!/^[a-z0-9][a-z0-9._@-]{2,63}$/.test(username)) {
    return "Username: at least 3 characters, using letters, numbers, dot, dash, underscore or @.";
  }
  if (password.length < MIN_PASSWORD) return `Password: at least ${MIN_PASSWORD} characters.`;
  if (password !== password.trim()) return "Password: no space at the start or end.";
  if (password !== confirm) return "The two passwords do not match.";
  return null;
}

function signupError(err: unknown): string {
  if (!(err instanceof ApiError)) return UNREACHABLE;
  if (err.status === 409) return "That username is taken. Choose another, or sign in if it is yours.";
  if ([403, 422, 429].includes(err.status)) return err.message;
  return UNREACHABLE;
}

function signinError(err: unknown): string {
  if (!(err instanceof ApiError)) return UNREACHABLE;
  if (err.status === 401) return "Incorrect username or password.";
  if (err.status === 429) {
    if (err.retryAfter && err.retryAfter < 60) return err.message; // busy, not locked out
    const mins = err.retryAfter ? Math.ceil(err.retryAfter / 60) : 15;
    return `Too many failed attempts. Try again in about ${mins} minute${mins === 1 ? "" : "s"}.`;
  }
  return UNREACHABLE;
}

export function LoginPage({ onSignedIn, signupOpen = true }: { onSignedIn: (u: User) => void; signupOpen?: boolean }) {
  // A first-time visitor creates an account; a returning one signs in.
  const [chosen, setChosen] = useState<Mode>(() => (hasAccountHere() ? "signin" : "signup"));
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mode: Mode = signupOpen ? chosen : "signin";
  const creating = mode === "signup";

  function show(next: Mode) {
    setChosen(next);
    setError(null);
    setPassword("");
    setConfirm("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const id = username.trim().toLowerCase();
    const problem = creating ? signupProblem(id, password, confirm) : null;
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user = creating
        ? await api.signup(id, name.trim(), password, remember)
        : await api.login(username, password, remember);
      rememberAccount();
      onSignedIn(user);
    } catch (err) {
      setError(creating ? signupError(err) : signinError(err));
      if (!creating) setPassword("");
    } finally {
      setBusy(false);
    }
  }

  const incomplete = !username || !password || (creating && (!name.trim() || !confirm));

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
        {signupOpen && (
          <div className="auth-tabs" role="tablist" aria-label="Account">
            <button type="button" role="tab" aria-selected={creating} onClick={() => show("signup")}>Create account</button>
            <button type="button" role="tab" aria-selected={!creating} onClick={() => show("signin")}>Sign in</button>
          </div>
        )}
        <h1 id="login-title">{creating ? "Create your account" : "Welcome back"}</h1>
        {creating && (
          <label>
            Your name
            <input key="name" autoFocus autoComplete="name" maxLength={64} value={name}
                   onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        <label>
          Username
          <input key={`username-${mode}`} autoFocus={!creating} autoComplete="username" autoCapitalize="none"
                 maxLength={64} value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label>
          Password
          <input key={`password-${mode}`} type="password" autoComplete={creating ? "new-password" : "current-password"}
                 placeholder={creating ? `At least ${MIN_PASSWORD} characters` : undefined} maxLength={256}
                 value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {creating && (
          <label>
            Confirm password
            <input type="password" autoComplete="new-password" maxLength={256} value={confirm}
                   onChange={(e) => setConfirm(e.target.value)} required />
          </label>
        )}
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Keep me signed in on this device
        </label>
        {error && <div className="note note-error" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy || incomplete}>
          {creating ? (busy ? "Creating your account…" : "Create account and continue") : busy ? "Signing in…" : "Sign in"}
        </button>
        {signupOpen && (
          <p className="auth-switch">
            {creating ? "Already have an account?" : "New here?"}{" "}
            <button type="button" className="link" onClick={() => show(creating ? "signin" : "signup")}>
              {creating ? "Sign in instead" : "Create one now"}
            </button>
          </p>
        )}
        <p className="fineprint">
          {creating
            ? "Your investigations are visible to you and the Sentinel AI team, not to other users. There is no email reset, so keep your password safe. Use synthetic or anonymised data only."
            : "Prototype for demonstration. Synthetic data and mock banking services only."}
        </p>
      </form>
    </div>
  );
}
