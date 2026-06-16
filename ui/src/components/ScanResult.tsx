// Renders a completed ScanResponse: status, coach advice, product details,
// ingredients, safety findings, and routine fit.
import type { ScanResponse, ScanStatus } from "../api/types";
import { LeafScore } from "./LeafScore";

const STATUS_META: Record<
  ScanStatus,
  { label: string; tone: string; blurb: string }
> = {
  complete: {
    label: "Complete",
    tone: "ok",
    blurb: "A full recommendation was produced.",
  },
  retake_required: {
    label: "Retake needed",
    tone: "warn",
    blurb: "The label couldn't be read — try a sharper, well-lit photo.",
  },
  action_needed: {
    label: "Action needed",
    tone: "warn",
    blurb: "The product identity or ingredients need confirmation.",
  },
  incomplete: {
    label: "Incomplete",
    tone: "danger",
    blurb: "The pipeline exited without advice.",
  },
};

function scorePct(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function safetyTone(score: number): string {
  if (score >= 0.75) return "ok";
  if (score >= 0.4) return "warn";
  return "danger";
}

export function ScanResult({ result }: { result: ScanResponse }) {
  const meta = STATUS_META[result.status];
  const safety = result.safety_report;
  const fit = result.routine_fit;

  return (
    <div className="scan-result">
      <div className={`banner banner-${meta.tone}`}>
        <strong>{meta.label}.</strong> {meta.blurb}
      </div>

      {result.coach_advice && (
        <section className="card coach-card">
          <h2 className="card-title">Your coach says</h2>
          {result.recommendation_score != null && (
            <div className="reco-score-banner">
              <div className="reco-score-head">
                <span className="reco-score-label">
                  How recommendable for you
                </span>
                <LeafScore score={result.recommendation_score} />
              </div>
              {result.recommendation_rationale && (
                <p className="reco-score-why">
                  {result.recommendation_rationale}
                </p>
              )}
            </div>
          )}
          <div className="coach-advice">{result.coach_advice}</div>
        </section>
      )}

      {result.added_product_id && (
        <div className="banner banner-ok">
          ✓ Saved to your routine.
        </div>
      )}

      {result.product && (
        <section className="card">
          <div className="product-card-head">
            <div>
              <div className="product-brand">{result.product.brand}</div>
              <div className="product-name">
                {result.product.product_name}
              </div>
            </div>
            {result.product.is_quasi_drug && (
              <span className="badge badge-quasi">医薬部外品</span>
            )}
          </div>

          <div className="meta-row">
            {result.model_used && (
              <Meta label="Source" value={result.model_used} />
            )}
            {result.ingredient_source && (
              <Meta label="Ingredients via" value={result.ingredient_source} />
            )}
            {result.detected_language && (
              <Meta label="Language" value={result.detected_language} />
            )}
            {result.inference_confidence != null && (
              <Meta
                label="Confidence"
                value={scorePct(result.inference_confidence)}
              />
            )}
          </div>
        </section>
      )}

      {safety && (
        <section className="card">
          <div className="card-title-row">
            <h2 className="card-title">Safety</h2>
            <span className={`score-pill score-${safetyTone(safety.safety_score)}`}>
              {scorePct(safety.safety_score)} safe
            </span>
          </div>

          {safety.warnings.length > 0 && (
            <ul className="finding-list">
              {safety.warnings.map((w, i) => (
                <li key={i} className="finding warn">
                  {w}
                </li>
              ))}
            </ul>
          )}

          {safety.ingredient_conflicts.length > 0 && (
            <Findings
              title="Conflicts"
              items={safety.ingredient_conflicts}
              tone="danger"
            />
          )}
          {safety.risk_ingredients.length > 0 && (
            <Findings
              title="Flagged ingredients"
              items={safety.risk_ingredients}
              tone="warn"
            />
          )}

          {safety.warnings.length === 0 &&
            safety.ingredient_conflicts.length === 0 &&
            safety.risk_ingredients.length === 0 && (
              <p className="muted">No safety flags. 👍</p>
            )}
        </section>
      )}

      {fit &&
        (fit.conflicts.length > 0 ||
          fit.redundancy.length > 0 ||
          fit.value_add.length > 0) && (
          <section className="card">
            <h2 className="card-title">Fit with your routine</h2>

            {fit.conflicts.length > 0 && (
              <div className="fit-block">
                <h3 className="fit-heading danger">Conflicts</h3>
                <ul className="finding-list">
                  {fit.conflicts.map((c, i) => (
                    <li key={i} className="finding danger">
                      <strong>vs {c.with_product}</strong> ({c.severity}):{" "}
                      {c.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {fit.redundancy.length > 0 && (
              <Findings
                title="Possibly redundant"
                items={fit.redundancy}
                tone="warn"
              />
            )}
            {fit.value_add.length > 0 && (
              <Findings
                title="Adds value for"
                items={fit.value_add}
                tone="ok"
              />
            )}
          </section>
        )}

      {result.standardized_ingredients.length > 0 && (
        <section className="card">
          <h2 className="card-title">
            Ingredients ({result.standardized_ingredients.length})
          </h2>
          <div className="ingredient-chips">
            {result.standardized_ingredients.map((ing, i) => (
              <span
                key={i}
                className={`ingredient-chip${ing.is_active ? " active" : ""}`}
                title={ing.name_raw}
              >
                {ing.name_standardized || ing.name_raw}
              </span>
            ))}
          </div>
          {result.unmatched_ingredients.length > 0 && (
            <p className="muted unmatched">
              Unmatched: {result.unmatched_ingredients.join(", ")}
            </p>
          )}
        </section>
      )}

      {result.web_sources.length > 0 && (
        <section className="card">
          <h2 className="card-title">Sources</h2>
          <ul className="source-list">
            {result.web_sources.map((s, i) => (
              <li key={i}>
                <a href={s} target="_blank" rel="noreferrer">
                  {s}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="meta">
      <span className="meta-label">{label}</span>
      <span className="meta-value">{value}</span>
    </div>
  );
}

function Findings({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: string;
}) {
  return (
    <div className="fit-block">
      <h3 className={`fit-heading ${tone}`}>{title}</h3>
      <ul className="finding-list">
        {items.map((item, i) => (
          <li key={i} className={`finding ${tone}`}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
