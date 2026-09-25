import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { Evaluation } from "./pages/Evaluation";
import { History } from "./pages/History";
import { SessionPage } from "./pages/SessionPage";

export function App() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">◆</span> CodePilot
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/evaluation">Evaluation</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sessions/:id" element={<SessionPage />} />
          <Route path="/history" element={<History />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="*" element={<div className="page">Page not found.</div>} />
        </Routes>
      </main>
    </div>
  );
}
