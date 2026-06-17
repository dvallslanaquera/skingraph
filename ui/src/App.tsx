import { useState } from "react";
import { UserPicker } from "./components/UserPicker";
import { useI18n, type Lang } from "./i18n";
import { LANGS, STRINGS } from "./i18n/strings";
import { CheckProduct } from "./pages/CheckProduct";
import { MyProfile } from "./pages/MyProfile";
import { MyRoutine } from "./pages/MyRoutine";

type View = "profile" | "routine" | "check";

const NAV: { id: View; icon: string }[] = [
  { id: "profile", icon: "👤" },
  { id: "routine", icon: "🧴" },
  { id: "check", icon: "📷" },
];

export default function App() {
  const { t, lang, setLang } = useI18n();
  const [view, setView] = useState<View>("check");

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">✦</span>
          <div>
            <div className="brand-name">SkinGraph</div>
            <div className="brand-sub">{t("brand.sub")}</div>
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
                <span className="nav-label">{t(`nav.${item.id}.label`)}</span>
                <span className="nav-hint">{t(`nav.${item.id}.hint`)}</span>
              </span>
            </button>
          ))}
        </nav>

        <div className="lang-toggle" role="group" aria-label="Language">
          {LANGS.map((l: Lang) => (
            <button
              key={l}
              type="button"
              className={`lang-option${lang === l ? " active" : ""}`}
              aria-pressed={lang === l}
              onClick={() => setLang(l)}
            >
              {STRINGS[l]["lang.name"]}
            </button>
          ))}
        </div>

        <footer className="sidebar-footer">LangGraph · FastAPI · Gemini</footer>
      </aside>

      <main className="content">
        {view === "profile" && <MyProfile />}
        {view === "routine" && <MyRoutine />}
        {view === "check" && <CheckProduct />}
      </main>
    </div>
  );
}
