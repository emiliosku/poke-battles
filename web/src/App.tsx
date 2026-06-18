import { Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Teams from "./pages/Teams";
import Battle from "./pages/Battle";
import Simulations from "./pages/Simulations";
import Leaderboard from "./pages/Leaderboard";
import Replays from "./pages/Replays";

function Nav() {
  return (
    <nav style={{ display: "flex", gap: 16, padding: "8px 16px", borderBottom: "1px solid #ccc" }}>
      <strong>Poké Battles</strong>
      <Link to="/">Dashboard</Link>
      <Link to="/teams">Teams</Link>
      <Link to="/battle">Battle</Link>
      <Link to="/simulations">Simulations</Link>
      <Link to="/leaderboard">Leaderboard</Link>
      <Link to="/replays">Replays</Link>
    </nav>
  );
}

export default function App() {
  return (
    <div style={{ fontFamily: "sans-serif", minHeight: "100vh", background: "#f5f5f5" }}>
      <Nav />
      <main style={{ padding: 16, maxWidth: 960, margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/battle" element={<Battle />} />
          <Route path="/battle/:id" element={<Battle />} />
          <Route path="/simulations" element={<Simulations />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/replays" element={<Replays />} />
        </Routes>
      </main>
    </div>
  );
}
