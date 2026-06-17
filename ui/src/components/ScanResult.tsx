// Renders a completed ScanResponse: status, coach advice, product details,
// ingredients, safety findings, and routine fit.
import type { ScanResponse, ScanStatus } from "../api/types";
import { useI18n } from "../i18n";
import { LeafScore } from "./LeafScore";

const STATUS_TONE: Record<ScanStatus, string> = {
  complete: "ok",
  retake_required: "warn",
  action_needed: "warn",
  incomplete: "danger",
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
  const { t, lang } = useI18n();
  const tone = STATUS_TONE[result.status];
  const safety = result.safety_report;
  const fit = result.routine_fit;

  const advice =
    (lang === "ja" ? result.coach_advice_ja : result.coach_advice_en) ??
    result.coach_advice;
  const rationale =
    lang === "ja"
      ? result.recommendation_rationale_ja
      : result.recommendation_rationale_en;

  return (
    <div className="scan-result">
      <div className={`banner banner-${tone}`}>
        <strong>{t(`scan.status.${result.status}.label`)}.</strong>{" "}
        {t(`scan.status.${result.status}.blurb`)}
      </div>

      {advice && (
        <section className="card coach-card">
          <h2 className="card-title">{t("scan.coachTitle")}</h2>
          {result.recommendation_score != null && (
            <div className="reco-score-banner">
              <div className="reco-score-head">
                <span className="reco-score-label">{t("scan.recoLabel")}</span>
                <LeafScore score={result.recommendation_score} />
              </div>
              {rationale && <p className="reco-score-why">{rationale}</p>}
            </div>
          )}
          <div className="coach-advice">{advice}</div>
        </section>
      )}

      {result.added_product_id && (
        <div className="banner banner-ok">{t("check.save.saved")}</div>
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
              <Meta label={t("scan.meta.source")} value={result.model_used} />
            )}
            {result.ingredient_source && (
              <Meta
                label={t("scan.meta.ingredientsVia")}
                value={result.ingredient_source}
              />
            )}
            {result.detected_language && (
              <Meta
                label={t("scan.meta.language")}
                value={result.detected_language}
              />
            )}
            {result.inference_confidence != null && (
              <Meta
                label={t("scan.meta.confidence")}
                value={scorePct(result.inference_confidence)}
              />
            )}
          </div>
        </section>
      )}

      {safety && (
        <section className="card">
          <div className="card-title-row">
            <h2 className="card-title">{t("scan.safety")}</h2>
            <span className={`score-pill score-${safetyTone(safety.safety_score)}`}>
              {t("scan.safety.safe", { pct: scorePct(safety.safety_score) })}
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
              title={t("scan.safety.conflicts")}
              items={safety.ingredient_conflicts}
              tone="danger"
            />
          )}
          {safety.risk_ingredients.length > 0 && (
            <Findings
              title={t("scan.safety.flagged")}
              items={safety.risk_ingredients}
              tone="warn"
            />
          )}

          {safety.warnings.length === 0 &&
            safety.ingredient_conflicts.length === 0 &&
            safety.risk_ingredients.length === 0 && (
              <p className="muted">{t("scan.safety.none")}</p>
            )}
        </section>
      )}

      {fit &&
        (fit.conflicts.length > 0 ||
          fit.redundancy.length > 0 ||
          fit.value_add.length > 0) && (
          <section className="card">
            <h2 className="card-title">{t("scan.fitTitle")}</h2>

            {fit.conflicts.length > 0 && (
              <div className="fit-block">
                <h3 className="fit-heading danger">{t("scan.fit.conflicts")}</h3>
                <ul className="finding-list">
                  {fit.conflicts.map((c, i) => (
                    <li key={i} className="finding danger">
                      <ConflictLine
                        product={c.with_product}
                        severity={c.severity}
                        reason={c.reason}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {fit.redundancy.length > 0 && (
              <Findings
                title={t("scan.fit.redundant")}
                items={fit.redundancy}
                tone="warn"
              />
            )}
            {fit.value_add.length > 0 && (
              <Findings
                title={t("scan.fit.valueAdd")}
                items={fit.value_add}
                tone="ok"
              />
            )}
          </section>
        )}

      {result.standardized_ingredients.length > 0 && (
        <section className="card">
          <h2 className="card-title">
            {t("scan.ingredients", {
              count: result.standardized_ingredients.length,
            })}
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
              {t("scan.unmatched", {
                list: result.unmatched_ingredients.join(", "),
              })}
            </p>
          )}
        </section>
      )}

      {result.web_sources.length > 0 && (
        <section className="card">
          <h2 className="card-title">{t("scan.sources")}</h2>
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

function ConflictLine({
  product,
  severity,
  reason,
}: {
  product: string;
  severity: string;
  reason: string;
}) {
  const { lang, term } = useI18n();
  const sev = term(severity);
  return lang === "ja" ? (
    <>
      <strong>{product}</strong>（{sev}）：{reason}
    </>
  ) : (
    <>
      <strong>vs {product}</strong> ({sev}): {reason}
    </>
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
