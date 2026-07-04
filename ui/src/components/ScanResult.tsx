// Renders a completed ScanResponse: status, the coach's structured card,
// product details, ingredients, safety findings, routine fit, and a stateless
// follow-up Q&A thread (kept in component state only — nothing server-side).
import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { ScanResponse, ScanStatus } from "../api/types";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";
import { ClockIcon, RepeatIcon } from "./icons";
import { LeafScore } from "./LeafScore";
import { Typewriter } from "./Typewriter";

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

// Show this many ingredient chips before collapsing behind a "show all" toggle.
const INGREDIENT_PREVIEW_COUNT = 12;

export function ScanResult({ result }: { result: ScanResponse }) {
  const { t, lang } = useI18n();
  const [showAllIngredients, setShowAllIngredients] = useState(false);
  const tone = STATUS_TONE[result.status];
  const safety = result.safety_report;
  const fit = result.routine_fit;

  // Safety findings are formatted server-side; the auditor emits a Japanese
  // rendering alongside the English one. Pick per locale, falling back to English
  // if the JA list is absent (e.g. an older backend response).
  const safetyWarnings =
    safety && lang === "ja" && safety.warnings_ja?.length
      ? safety.warnings_ja
      : (safety?.warnings ?? []);
  const safetyConflicts =
    safety && lang === "ja" && safety.ingredient_conflicts_ja?.length
      ? safety.ingredient_conflicts_ja
      : (safety?.ingredient_conflicts ?? []);

  // The coach card in the UI's language; the LLM-phrased routine-fit notes
  // (used for the Routine Fit section when present, since they match the UI
  // language — the deterministic routine_fit stays as the fallback).
  const coach = result.coach;
  const card = coach ? (lang === "ja" ? coach.japanese : coach.english) : null;
  const coachFit = coach
    ? lang === "ja"
      ? coach.routine_japanese
      : coach.routine_english
    : null;
  const hasCoachFit =
    !!coachFit &&
    (coachFit.risks.length > 0 ||
      coachFit.redundancy.length > 0 ||
      coachFit.value_add.length > 0);

  // "AM" / "PM" / "AM & PM" localised; unknown values fall back to the raw token.
  function timingLabel(timing: string): string {
    const key = `scan.coach.timing.${timing}`;
    const label = t(key);
    return label === key ? timing : label;
  }

  // "registry" / "label" / "web" humanised; unknown values fall back to the raw token.
  function sourceLabel(source: string): string {
    const key = `scan.meta.source.${source}`;
    const label = t(key);
    return label === key ? source : label;
  }

  return (
    <div className="scan-result">
      <div className={`banner banner-${tone}`}>
        <strong>{t(`scan.status.${result.status}.label`)}.</strong>{" "}
        {t(`scan.status.${result.status}.blurb`)}
      </div>

      {card && (
        <section className="card coach-card">
          <h2 className="card-title">{t("scan.coachTitle")}</h2>

          {card.verdict && (
            <Typewriter text={card.verdict} className="coach-verdict" />
          )}

          {coach?.recommendation_score != null && (
            <div className="reco-score-banner">
              <div className="reco-score-head">
                <span className="reco-score-label">{t("scan.recoLabel")}</span>
                <LeafScore score={coach.recommendation_score} />
              </div>
              {card.recommendation_rationale && (
                <p className="reco-score-why">{card.recommendation_rationale}</p>
              )}
            </div>
          )}

          {card.purpose && <p className="coach-purpose">{card.purpose}</p>}

          {(card.timing || card.frequency) && (
            <div className="coach-badges">
              {card.timing && (
                <span className="badge badge-coach" title={t("scan.coach.timing")}>
                  <ClockIcon size={14} />
                  {timingLabel(card.timing)}
                </span>
              )}
              {card.frequency && (
                <span className="badge badge-coach" title={t("scan.coach.frequency")}>
                  <RepeatIcon size={14} />
                  {card.frequency}
                </span>
              )}
            </div>
          )}

          {card.warnings.length > 0 && (
            <Findings
              title={t("scan.coach.warnings")}
              items={card.warnings}
              tone="warn"
            />
          )}
          {card.application_notes.length > 0 && (
            <Findings
              title={t("scan.coach.howToApply")}
              items={card.application_notes}
              tone="ok"
            />
          )}
          {card.routine_integration && (
            <div className="fit-block">
              <h3 className="fit-heading ok">{t("scan.coach.fit")}</h3>
              <p className="coach-integration">{card.routine_integration}</p>
            </div>
          )}
        </section>
      )}

      {!card && result.notice && (
        <section className="card coach-card">
          <h2 className="card-title">{t("scan.coachTitle")}</h2>
          <div className="coach-advice">{result.notice[lang]}</div>
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

          {result.ingredient_source && (
            <div className="meta-row">
              <Meta
                label={t("scan.meta.source")}
                value={sourceLabel(result.ingredient_source)}
              />
            </div>
          )}
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

          {safetyWarnings.length > 0 && (
            <ul className="finding-list">
              {safetyWarnings.map((w, i) => (
                <li key={i} className="finding warn">
                  {w}
                </li>
              ))}
            </ul>
          )}

          {safetyConflicts.length > 0 && (
            <Findings
              title={t("scan.safety.conflicts")}
              items={safetyConflicts}
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

          {safetyWarnings.length === 0 &&
            safetyConflicts.length === 0 &&
            safety.risk_ingredients.length === 0 && (
              <p className="muted">{t("scan.safety.none")}</p>
            )}
        </section>
      )}

      {hasCoachFit ? (
        <section className="card">
          <h2 className="card-title">{t("scan.fitTitle")}</h2>
          {coachFit.risks.length > 0 && (
            <Findings
              title={t("scan.fit.conflicts")}
              items={coachFit.risks}
              tone="danger"
            />
          )}
          {coachFit.redundancy.length > 0 && (
            <Findings
              title={t("scan.fit.redundant")}
              items={coachFit.redundancy}
              tone="warn"
            />
          )}
          {coachFit.value_add.length > 0 && (
            <Findings
              title={t("scan.fit.valueAdd")}
              items={coachFit.value_add}
              tone="ok"
            />
          )}
        </section>
      ) : (
        fit &&
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
        )
      )}

      {result.standardized_ingredients.length > 0 && (
        <section className="card">
          <h2 className="card-title">
            {t("scan.ingredients", {
              count: result.standardized_ingredients.length,
            })}
          </h2>
          <div className="ingredient-chips">
            {(showAllIngredients
              ? result.standardized_ingredients
              : result.standardized_ingredients.slice(0, INGREDIENT_PREVIEW_COUNT)
            ).map((ing, i) => (
              <span
                key={i}
                className={`ingredient-chip${ing.is_active ? " active" : ""}`}
                title={ing.name_raw}
              >
                {ing.name_standardized || ing.name_raw}
              </span>
            ))}
            {result.standardized_ingredients.length > INGREDIENT_PREVIEW_COUNT && (
              <button
                type="button"
                className="chip-toggle"
                onClick={() => setShowAllIngredients((v) => !v)}
              >
                {showAllIngredients
                  ? t("scan.ingredients.showLess")
                  : t("scan.ingredients.showAll", {
                      count: result.standardized_ingredients.length,
                    })}
              </button>
            )}
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

      {result.status === "complete" && <FollowupChat result={result} />}
    </div>
  );
}

// Stateless follow-up Q&A: each question travels with the scan grounding the
// client already holds; the thread lives only in this component's state.
function FollowupChat({ result }: { result: ScanResponse }) {
  const { t, lang } = useI18n();
  const { currentUserId } = useUsers();

  const [thread, setThread] = useState<{ q: string; a: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setError(null);
    try {
      const res = await api.followup({
        brand: result.product?.brand ?? "",
        product_name: result.product?.product_name ?? "",
        standardized_ingredients: result.standardized_ingredients,
        safety_report: result.safety_report,
        routine_fit: result.routine_fit,
        question: q,
        lang,
        user_id: currentUserId ?? undefined,
      });
      setThread((prev) => [...prev, { q, a: res.answer }]);
      setQuestion("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="card followup-card">
      <h2 className="card-title">{t("scan.followup.title")}</h2>

      {thread.length > 0 && (
        <div className="followup-thread">
          {thread.map((turn, i) => (
            <div key={i} className="followup-turn">
              <p className="followup-q">{turn.q}</p>
              <p className="followup-a">{turn.a}</p>
            </div>
          ))}
        </div>
      )}

      {error && <div className="banner banner-error">{error}</div>}

      <div className="followup-row">
        <input
          type="text"
          className="followup-input"
          value={question}
          maxLength={500}
          placeholder={t("scan.followup.placeholder")}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void ask();
          }}
          disabled={asking}
        />
        <button
          className="btn btn-primary"
          onClick={() => void ask()}
          disabled={asking || !question.trim()}
        >
          {asking ? t("scan.followup.thinking") : t("scan.followup.send")}
        </button>
      </div>
    </section>
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
