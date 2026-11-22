import { useEffect, useState } from "react";
import { Logo } from "./components/Icons";
import { Spinner } from "./components/ui";
import { rememberAccount } from "./lib/account";
import { ApiError, api, setUnauthorizedHandler } from "./lib/api";
import { navigate, useRoute } from "./lib/router";
import type { User } from "./lib/types";
import { CasePage } from "./pages/CasePage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { QueuePage } from "./pages/QueuePage";
import { RunPage } from "./pages/RunPage";

type AuthState = { status: "checking" } | { status: "signed-out"; reason?: string } | { status: "signed-in"; user: User };

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "checking" });
  const [writer, setWriter] = useState<string | null>(null);
  const [signupOpen, setSignupOpen] = useState(true);
  const route = useRoute();

  useEffect(() => {
    // A returning analyst with a valid session goes straight in.
    setUnauthorizedHandler(() => setAuth({ status: "signed-out", reason: "Your session has ended. Please sign in again." }));
    api.me()
      .then((user) => {
        rememberAccount();
        setAuth({ status: "signed-in", user });
      })
      .catch((e) => setAuth({ status: "signed-out", reason: e instanceof ApiError && e.status !== 401 ? "The service is waking up or unreachable; try again shortly." : undefined }));
    api.health().then((h) => {
      setWriter(h.report_writer ?? null);
      setSignupOpen(h.signup_open !== false);
    }).catch(() => setWriter(null));
  }, []);

  if (auth.status === "checking") return <div className="center"><Spinner label="Connecting…" /></div>;
  if (auth.status === "signed-out") {
    return (
      <>
        {auth.reason && <div className="toast">{auth.reason}</div>}
        <LoginPage signupOpen={signupOpen} onSignedIn={(user) => setAuth({ status: "signed-in", user })} />
      </>
    );
  }

  async function signOut() {
    try { await api.logout(); } finally {
      navigate("/"); // the next person to sign in here must not land on this person's case
      setAuth({ status: "signed-out" });
    }
  }

  const inCases = route.name === "queue" || route.name === "case";
  return (
    <div className={`app app-${route.name}`}>
      <header className="topbar no-print">
        <button className="brand" onClick={() => navigate("/")}><Logo /><span>Sentinel AI</span></button>
        <div className="topbar-right">
          <nav aria-label="Main">
            <a href="#/" className={inCases ? "" : "nav-on"}>Investigate</a>
            <a href="#/cases" className={inCases ? "nav-on" : ""}>Cases</a>
          </nav>
          {writer && <span className="pill pill-live"><i />{writer === "groq" ? "AI: Groq" : "AI: offline"}</span>}
          <button className="btn btn-ghost btn-xs" onClick={signOut} title={`Signed in as ${auth.user.display_name} (${auth.user.username})`}>Sign out</button>
        </div>
      </header>
      <main>
        {route.name === "home" && <HomePage />}
        {route.name === "run" && <RunPage key={route.runId} runId={route.runId} />}
        {route.name === "queue" && <QueuePage />}
        {route.name === "case" && <CasePage key={route.caseId} caseId={route.caseId} tab={route.tab} />}
      </main>
    </div>
  );
}
