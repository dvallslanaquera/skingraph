// Small inline flag chips for the language toggle. English is drawn as a split
// UK / US flag (the app's two English locales); Japanese as the hinomaru.
export function Flag({ lang }: { lang: "en" | "ja" }) {
  if (lang === "ja") {
    return (
      <svg className="lang-flag" viewBox="0 0 20 14" aria-hidden="true">
        <rect width="20" height="14" fill="#ffffff" />
        <circle cx="10" cy="7" r="3.6" fill="#bc002d" />
      </svg>
    );
  }
  return (
    <svg className="lang-flag" viewBox="0 0 20 14" aria-hidden="true">
      {/* UK half */}
      <rect x="0" y="0" width="10" height="14" fill="#012169" />
      <path d="M0 0 10 14 M10 0 0 14" stroke="#ffffff" strokeWidth="2.4" />
      <path d="M0 0 10 14 M10 0 0 14" stroke="#c8102e" strokeWidth="1" />
      <path d="M5 0V14 M0 7H10" stroke="#ffffff" strokeWidth="3" />
      <path d="M5 0V14 M0 7H10" stroke="#c8102e" strokeWidth="1.6" />
      {/* US half */}
      <rect x="10" y="0" width="10" height="14" fill="#ffffff" />
      <g fill="#b31942">
        <rect x="10" y="0" width="10" height="2" />
        <rect x="10" y="4" width="10" height="2" />
        <rect x="10" y="8" width="10" height="2" />
        <rect x="10" y="12" width="10" height="2" />
      </g>
      <rect x="10" y="0" width="5.6" height="7" fill="#0a3161" />
      <g fill="#ffffff">
        <circle cx="11.4" cy="1.7" r="0.5" />
        <circle cx="13" cy="1.7" r="0.5" />
        <circle cx="14.4" cy="1.7" r="0.5" />
        <circle cx="12.2" cy="3.5" r="0.5" />
        <circle cx="13.8" cy="3.5" r="0.5" />
        <circle cx="11.4" cy="5.3" r="0.5" />
        <circle cx="13" cy="5.3" r="0.5" />
        <circle cx="14.4" cy="5.3" r="0.5" />
      </g>
    </svg>
  );
}
