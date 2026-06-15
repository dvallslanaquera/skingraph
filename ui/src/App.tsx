import { useState } from "react";
import { UserPicker } from "./components/UserPicker";
import { CheckProduct } from "./pages/CheckProduct";
import { MyProfile } from "./pages/MyProfile";
import { MyRoutine } from "./pages/MyRoutine";

type View = "profile" | "routine" | "check";

const NAV: { id: View; label: string; icon: string; hint: string }[] = [
  { id: "profile", label: "My Profile", icon: "👤", hint: "Your skin data" },
  { id: "routine", label: "My Routine", icon: "🧴", hint: "Products you use" },
  { id: "check", label: "Check Product", icon: "📷", hint: "Scan & get advice" },
];

export default function App() {
  const [view, setView] = useState<View>("check");

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">✦</span>
          <div>
            <div className="brand-name">SkinGraph</div>
            <div className="brand-sub">Skincare Coach</div>
          </div>
        </div>

        <UserPicker />

        <nav className="nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              className={`nav-item${view === item.id ? " active" : ""}`}
              onClick={() => setView(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-text">
                <span className="nav-label">{item.label}</span>
                <span className="nav-hint">{item.hint}</span>
              </span>
            </button>
          ))}
        </nav>

        <footer className="sidebar-footer">
          LangGraph · FastAPI · Gemini
        </footer>
      </aside>

      <main className="content">
        {view === "profile" && <MyProfile />}
        {view === "routine" && <MyRoutine />}
        {view === "check" && <CheckProduct />}
      </main>
    </div>
  );
}
