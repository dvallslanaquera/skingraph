// A 0–5 "leaf" score, shared by the routine dashboard and a scan's coach card.
export function LeafScore({ score }: { score: number }) {
  return (
    <span className="leaf-score" aria-label={`Score ${score} of 5`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <LeafIcon key={i} filled={i < score} />
      ))}
    </span>
  );
}

function LeafIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      className={`leaf${filled ? " filled" : ""}`}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 19c0-8 6-14 14-14 0 8-6 14-14 14z" />
      <path d="M5 19c3-5 7-8 11-9" stroke="currentColor" fill="none" />
    </svg>
  );
}
