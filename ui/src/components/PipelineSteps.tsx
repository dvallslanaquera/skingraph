// Decorative pipeline indicator shown while a scan runs.
//
// `activeStep` (1-based, from the /scan/stream `stage` events) drives which
// stages are revealed, so the UI reflects real pipeline progress instead of a
// fake timer. The streaming endpoint maps each graph node to one of these steps.
import { useI18n } from "../i18n";

export function PipelineSteps({
  userName,
  activeStep = 1,
}: {
  userName?: string;
  activeStep?: number;
}) {
  const { t } = useI18n();
  const who = userName?.trim() || t("pipeline.you");
  const stages = [
    t("pipeline.step1"),
    t("pipeline.step2"),
    t("pipeline.step3"),
    t("pipeline.step4"),
    t("pipeline.step5", { name: who }),
  ];
  // activeStep is 1-based; clamp to the stage range and convert to a 0-based index.
  const active = Math.max(0, Math.min(activeStep - 1, stages.length - 1));

  return (
    <div className="card pipeline">
      <h2 className="card-title">{t("pipeline.title")}</h2>
      <ol className="pipeline-steps">
        {/* Reveal the steps up to the active one; each new <li> fades in on mount. */}
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