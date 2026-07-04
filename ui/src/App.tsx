import { useEffect, useState, type ComponentType } from "react";
import { Flag } from "./components/Flag";
import { CheckIcon, ProfileIcon, RoutineIcon } from "./components/icons";
import { UserMenu } from "./components/UserPicker";
import { useI18n, type Lang } from "./i18n";
import { LANGS, STRINGS } from "./i18n/strings";
import { CheckProduct } from "./pages/CheckProduct";
import { MyProfile } from "./pages/MyProfile";
import { MyRoutine } from "./pages/MyRoutine";

type View = "profile" | "routine" | "check";

const NAV: { id: View; Icon: ComponentType<{ size?: number }> }[] = [
  { id: "profile", Icon: ProfileIcon },
  { id: "routine", Icon: RoutineIcon },
  { id: "check", Icon: CheckIcon },
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
      <header className="topbar">
        <div className="topbar-inner">
          <a className="topbar-logo" href="/" aria-label="SkinGraph home">
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
            SkinGraph
          </a>

          {/* tabs sit immediately after the logo */}
          <nav className="topbar-nav" aria-label="Primary">
            {NAV.map((item) => (
              <button
                key={item.id}
                className={`topbar-link${view === item.id ? " active" : ""}`}
                aria-current={view === item.id ? "page" : undefined}
                onClick={() => goTo(item.id)}
              >
                <span className="nav-icon" aria-hidden="true">
                  <item.Icon size={18} />
                </span>
                <span>{t(`nav.${item.id}.label`)}</span>
              </button>
            ))}
          </nav>

          <div className="topbar-spacer" />

          <div className="topbar-right">
            <div className="topbar-lang" role="group" aria-label="Language">
              {LANGS.map((l: Lang) => (
                <button
                  key={l}
                  type="button"
                  className={`topbar-lang-btn${lang === l ? " active" : ""}`}
                  aria-pressed={lang === l}
                  onClick={() => setLang(l)}
                >
                  <Flag lang={l} />
                  {STRINGS[l]["lang.name"]}
                </button>
              ))}
            </div>

            {/* Persistent primary action: jump to a scan. Hidden once you're on
               the Check tab, where it would be redundant. */}
            {view !== "check" && (
              <button
                className="btn btn-primary topbar-cta"
                onClick={() => goTo("check")}
              >
                {t("check.scan")}
              </button>
            )}

            <UserMenu />
          </div>
        </div>
      </header>

      <main className="content">
        {view === "profile" && <MyProfile />}
        {view === "routine" && <MyRoutine />}
        {view === "check" && <CheckProduct />}

        <footer className="app-foot">
          <span>Created with ❤️ by David</span>
          <span className="app-foot-sep" aria-hidden="true">·</span>
          <span className="app-foot-version">v{__APP_VERSION__}</span>
        </footer>
      </main>

      {/* on narrow screens the tabs relocate here */}
      <nav className="bottom-nav" aria-label="Primary">
        {NAV.map((item) => (
          <button
            key={item.id}
            className={`bottom-nav-item${view === item.id ? " active" : ""}`}
            aria-current={view === item.id ? "page" : undefined}
            onClick={() => goTo(item.id)}
          >
            <span className="nav-icon" aria-hidden="true">
              <item.Icon size={22} />
            </span>
            <span>{t(`nav.${item.id}.label`)}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}