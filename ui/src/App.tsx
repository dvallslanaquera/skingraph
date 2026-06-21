import { useEffect, useState } from "react";
import { Flag } from "./components/Flag";
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

const VIEWS = NAV.map((n) => n.id);

// Each tab lives at its own hash URL (e.g. /app#routine), so tabs are
// shareable/bookmarkable and the browser Back/Forward buttons move between them.
// An unknown or missing hash (e.g. a bare /app from the landing page) falls back
// to the Check tab.
function viewFromHash(): View {
  const hash = window.location.hash.replace(/^#/, "");
  return VIEWS.includes(hash as View) ? (hash as View) : "check";
}

export default function App() {
  const { t, lang, setLang } = useI18n();
  const [view, setView] = useState<View>(viewFromHash);

  useEffect(() => {
    // Browser Back/Forward (and any manual hash edit) re-syncs the active tab.
    const onHashChange = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHashChange);
    // Normalise a bare /app into /app#<tab> without adding a history entry.
    if (!window.location.hash) {
      window.history.replaceState(null, "", `#${view}`);
    }
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Navigate by updating the hash; the hashchange listener above sets `view`.
  const goTo = (next: View) => {
    window.location.hash = next;
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            {/* leaf + cat-ear mark — matches the landing page (ui/index.html) */}
            <svg viewBox="0 0 34 34" fill="none">
              <circle cx="17" cy="17" r="17" fill="#e6f1ea" />
              <path d="M9 24c0-8 6-14 16-15-1 10-7 16-16 15Z" fill="#6db48c" />
              <path
                d="M9 24 24 9"
                stroke="#fff"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
              <path
                d="M21 11.5l1.6-3 1.4 3M11 21.5l-2.6.6 1.7-2.2"
                stroke="#4e9e78"
                strokeWidth="1.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
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
              onClick={() => goTo(item.id)}
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
              <Flag lang={l} />
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
