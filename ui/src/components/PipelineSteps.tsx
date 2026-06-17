// Decorative pipeline indicator shown while a scan runs.
//
// The backend is a single blocking /scan call, so we can't stream true per-node
// progress; instead we advance through the known stages on a timer to give the
// user a sense of what's happening during the wait.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";

export function PipelineSteps({ userName }: { userName?: string }) {
  const { t } = useI18n();
  const who = userName?.trim() || t("pipeline.you");
  const stages = [
    t("pipeline.step1"),
    t("pipeline.step2"),
    t("pipeline.step3"),
    t("pipeline.step4"),
    t("pipeline.step5", { name: who }),
  ];
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
      <h2 className="card-title">{t("pipeline.title")}</h2>
      <ol className="pipeline-steps">
        {/* Reveal the steps one at a time; each new <li> fades in on mount. */}
        {stages.map((label, i) =>
          i <= active ? (
            <li
              key={label}
              className={`pipeline-step fade-in${i < active ? " done" : " active"}`}
            >
              <span className="pipeline-dot">{i < active ? "✓" : i + 1}</span>
              <span className="pipeline-text">
                <span className="pipeline-label">{label}</span>
              </span>
            </li>
          ) : null,
        )}
      </ol>
      <p className="muted pipeline-note">{t("pipeline.note")}</p>
    </div>
  );
}
