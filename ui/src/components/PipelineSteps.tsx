// Decorative pipeline indicator shown while a scan runs.
//
// The backend is a single blocking /scan call, so we can't stream true per-node
// progress; instead we advance through the known stages on a timer to give the
// user a sense of what's happening during the wait.
import { useEffect, useState } from "react";

function stagesFor(userName: string): string[] {
  return [
    "Scanning the picture…",
    "Extracting ingredients…",
    "Looking for dangerous ingredients…",
    "Comparing to your routine…",
    `Creating a recommendation for ${userName}…`,
  ];
}

export function PipelineSteps({ userName }: { userName?: string }) {
  const stages = stagesFor(userName?.trim() || "you");
  const [active, setActive] = useState(0);

  useEffect(() => {
    // Advance roughly every few seconds; stop on the last stage and let the
    // real response replace this component when it lands.
    const id = setInterval(() => {
      setActive((i) => Math.min(i + 1, stages.length - 1));
    }, 2500);
    return () => clearInterval(id);
  }, [stages.length]);

  return (
    <div className="card pipeline">
      <h2 className="card-title">Analysing…</h2>
      <ol className="pipeline-steps">
        {stages.map((label, i) => (
          <li
            key={label}
            className={`pipeline-step${
              i < active ? " done" : i === active ? " active" : ""
            }`}
          >
            <span className="pipeline-dot">{i < active ? "✓" : i + 1}</span>
            <span className="pipeline-text">
              <span className="pipeline-label">{label}</span>
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
