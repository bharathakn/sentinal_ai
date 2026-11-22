import { useEffect, useState } from "react";
import { Spinner } from "./components/ui";
import { ApiError, api, setUnauthorizedHandler } from "./lib/api";
import { navigate, useRoute } from "./lib/router";
import type { User } from "./lib/types";
import { CasePage } from "./pages/CasePage";
import { LoginPage } from "./pages/LoginPage";
import { QueuePage } from "./pages/QueuePage";

type AuthState = { status: "checking" } | { status: "signed-out"; reason?: string } | { status: "signed-in"; user: User };

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "checking" });
  const route = useRoute();

  useEffect(() => {
    // A returning analyst with a valid session goes straight to the queue.
    setUnauthorizedHandler(() => setAuth({ status: "signed-out", reason: "Your session has ended. Please sign in again." }));
    api.me()
      .then((user) => setAuth({ status: "signed-in", user }))
      .catch((e) => setAuth({ status: "signed-out", reason: e instanceof ApiError && e.status !== 401 ? "The service is waking up or unreachable; try again shortly." : undefined }));
  }, []);

  if (auth.status === "checking") return <div className="center"><Spinner label="Connecting…" /></div>;
  if (auth.status === "signed-out") {
    return (
      <>
        {auth.reason && <div className="toast">{auth.reason}</div>}
        <LoginPage onSignedIn={(user) => setAuth({ status: "signed-in", user })} />
      </>
    );
  }

  async function signOut() {
    try { await api.logout(); } finally { setAuth({ status: "signed-out" }); }
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => navigate("/")}><img src="/favicon.svg" alt="" /><span>Sentinel AI</span></button>
        <span className="proto-pill" title="Synthetic and mock data only; not connected to banking systems">Prototype · synthetic data</span>
        <div className="topbar-right">
          <span className="user" title={auth.user.username}>{auth.user.display_name}</span>
          <button className="btn btn-ghost btn-xs" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <main>
        {route.name === "queue" && <QueuePage />}
        {route.name === "case" && <CasePage key={route.caseId} caseId={route.caseId} tab={route.tab} />}
      </main>
    </div>
  );
}
