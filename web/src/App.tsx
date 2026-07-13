import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import Battle from "./pages/Battle";
import Dashboard from "./pages/Dashboard";
import Leaderboard from "./pages/Leaderboard";
import Practice from "./pages/Practice";
import Replays, { ReplayDetail, SharedReplay } from "./pages/Replays";
import SignIn from "./pages/SignIn";
import Simulations from "./pages/Simulations";
import SpriteDebug from "./pages/SpriteDebug";
import Teams from "./pages/Teams";

// Dev tools (the /debug/sprites page) are enabled when either:
//   * Vite is running in dev mode (npm run dev), or
//   * the production build was compiled with VITE_ENABLE_DEBUG=true.
// Set the env var in the deploy env (e.g. docker compose) to opt in
// to the debug page in production. Default is dev-only.
const SHOW_DEBUG_TOOLS =
  import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === "true";

function Nav() {
  const { user, loading, logout } = useAuth();
  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <span className="brand-mark" aria-hidden="true" />
        <span>Poké Battles</span>
      </Link>
      <nav className="nav" aria-label="Primary navigation">
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/teams">Teams</NavLink>
        <NavLink to="/battle">Battle</NavLink>
        <NavLink to="/practice">Practice</NavLink>
        <NavLink to="/simulations">Simulations</NavLink>
        <NavLink to="/leaderboard">Leaderboard</NavLink>
        <NavLink to="/replays">Replays</NavLink>
        {SHOW_DEBUG_TOOLS && <NavLink to="/debug/sprites">Debug</NavLink>}
      </nav>
      <div className="userbox">
        {loading && <span>Checking session...</span>}
        {!loading && user && (
          <>
            {user.avatar_url && <img className="avatar" src={user.avatar_url} alt="" />}
            <span>{user.display_name || user.id}</span>
            <button className="button ghost" type="button" onClick={() => void logout()}>
              Logout
            </button>
          </>
        )}
        {!loading && !user && <Link className="button secondary" to="/signin">Sign in</Link>}
      </div>
    </header>
  );
}

function NotFound() {
  return (
    <section className="page">
      <div className="hero">
        <span className="eyebrow">404</span>
        <h1>Route fled.</h1>
        <p>The page you requested is not in this battle party. Pick a destination from the navigation above, or head back to the dashboard.</p>
        <div className="row" style={{ marginTop: 6 }}>
          <Link className="button" to="/">Back to dashboard</Link>
          <Link className="button secondary" to="/replays">Browse replays</Link>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const isSharedReplay = location.pathname.startsWith("/shared/");
  useEffect(() => {
    if (loading || !user) return;
    const returnTo = window.sessionStorage.getItem("poke-battles:return-to");
    if (!returnTo) return;
    window.sessionStorage.removeItem("poke-battles:return-to");
    if (`${location.pathname}${location.search}` !== returnTo) navigate(returnTo, { replace: true });
  }, [loading, location.pathname, location.search, navigate, user]);
  return (
    <div className="app-shell">
      {!isSharedReplay && <Nav />}
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/teams" element={<Teams />} />
        <Route path="/battle" element={<Battle />} />
        <Route path="/battle/:id" element={<Battle />} />
        <Route path="/practice" element={<Practice />} />
        <Route path="/practice/:id" element={<Practice />} />
        <Route path="/simulations" element={<Simulations />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/replays" element={<Replays />} />
        <Route path="/replays/:battleId" element={<ReplayDetail />} />
        <Route path="/shared/:token" element={<SharedReplay />} />
        {SHOW_DEBUG_TOOLS && <Route path="/debug/sprites" element={<SpriteDebug />} />}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}
