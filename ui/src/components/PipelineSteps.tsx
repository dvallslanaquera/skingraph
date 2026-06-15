// Decorative pipeline indicator shown while a scan runs.
//
// The backend is a single blocking /scan call, so we can't stream true per-node
// progress; instead we advance through the known LangGraph stages on a timer to
// illustrate the architecture during a demo.
import { useEffect, useState } from "react";

const STAGES = [
  { label: "Scanner", detail: "Gemini reads the label" },
  { label: "Normalizer", detail: "Map names → INCI" },
  { label: "Auditor", detail: "Check ingredient safety" },
  { label: "Routine fit", detail: "Compare to your shelf" },
  { label: "Coach", detail: "Write your advice" },
];

export function PipelineSteps() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    // Advance roughly every few seconds; stop on the last stage and let the
    // real response replace this component when it lands.
    const id = setInterval(() => {
      setActive((i) => Math.min(i + 1, STAGES.length - 1));
    }, 2500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="card pipeline">
      <h2 className="card-title">Analysing…</h2>
      <ol className="pipeline-steps">
        {STAGES.map((s, i) => (
          <li
            key={s.label}
            className={`pipeline-step${
              i < active ? " done" : i === active ? " active" : ""
            }`}
          >
            <span className="pipeline-dot">
              {i < active ? "✓" : i + 1}
            </span>
            <span className="pipeline-text">
              <span className="pipeline-label">{s.label}</span>
              <span className="pipeline-detail">{s.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="muted pipeline-note">
        A real scan takes ~8–40s depending on the path (database hit, label OCR,
        or web fallback).
      </p>
    </div>
  );
}
