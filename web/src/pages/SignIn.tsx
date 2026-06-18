import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function SignIn() {
  const { user, login, error: authError } = useAuth();
  const [providers, setProviders] = useState<Record<"github" | "google", boolean>>({ github: false, google: false });
  const [error, setError] = useState("");

  useEffect(() => {
    api.auth.providers().then(setProviders).catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (user) return <Navigate to="/" replace />;

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">Trainer access</span>
        <h1>Enter the arena.</h1>
        <p>Sign in with a free OAuth provider. Sessions are stored in this app with HTTP-only cookies and OCI PostgreSQL.</p>
      </section>
      <section className="grid two">
        <div className="card stack">
          <h2>Choose provider</h2>
          {(error || authError) && <div className="notice error">{error || authError}</div>}
          <button className="button" type="button" disabled={!providers.github} onClick={() => login("github")}>
            Continue with GitHub
          </button>
          <button className="button secondary" type="button" disabled={!providers.google} onClick={() => login("google")}>
            Continue with Google
          </button>
          {!providers.github && !providers.google && (
            <div className="notice">No OAuth providers are configured yet. Add client IDs/secrets to the API environment.</div>
          )}
        </div>
        <div className="card stack">
          <h2>Why this auth?</h2>
          <p>No paid SaaS auth dependency. GitHub and Google OAuth are free; this app owns users, sessions, and team permissions in Postgres.</p>
          <span className="badge green">Free all the way</span>
        </div>
      </section>
    </main>
  );
}
