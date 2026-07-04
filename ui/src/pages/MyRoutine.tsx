// "My Routine" — a minimal dashboard of the user's saved "shelf".
//
// Products are added by scanning a label (the VLM pipeline extracts the product
// and saves it via /scan with add_to_routine), with a manual form kept as a
// fallback for products that won't scan. The dashboard shows the product list,
// the routine's amortized monthly cost (USD), an AM/PM split with per-product
// application notes, and a goal-coverage chart scored out of 5 leaves.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type {
  RoutineDashboard,
  RoutineDashboardCard,
  ScanResponse,
} from "../api/types";
import { CameraIcon, RoutineIcon } from "../components/icons";
import { LeafScore } from "../components/LeafScore";
import { NoUser } from "../components/NoUser";
import { PipelineSteps } from "../components/PipelineSteps";
import { ScanResult } from "../components/ScanResult";
import { TagInput } from "../components/TagInput";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";
import { formatMonthlyTotal, formatProductPrice } from "../i18n/strings";

export function MyRoutine() {
  const { t, lang } = useI18n();
  const { currentUserId } = useUsers();

  const [dashboard, setDashboard] = useState<RoutineDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // `lang` is a dep so switching the UI language re-fetches the dashboard with
  // per-product notes in the new language.
  const load = useCallback(
    async (userId: string) => {
      setLoading(true);
      setError(null);
      try {
        setDashboard(await api.getRoutineDashboard(userId, lang));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [lang],
  );

  useEffect(() => {
    if (currentUserId) void load(currentUserId);
    else setDashboard(null);
  }, [currentUserId, load]);

  if (!currentUserId) return <NoUser action={t("noUser.action.routine")} />;

  async function handleRemove(productId: string) {
    if (!currentUserId) return;
    setError(null);
    try {
      await api.removeRoutineProduct(productId);
      await load(currentUserId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const products = dashboard?.products ?? [];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t("routine.title")}</h1>
          <p className="page-sub">{t("routine.sub")}</p>
        </div>
        {!adding && (
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            {t("routine.addProduct")}
          </button>
        )}
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {adding && (
        <AddProductPanel
          userId={currentUserId}
          onChanged={() => currentUserId && load(currentUserId)}
          onClose={() => setAdding(false)}
        />
      )}

      {loading ? (
        <div className="card">{t("routine.loading")}</div>
      ) : products.length === 0 ? (
        !adding && (
          <div className="empty-state">
            <div className="empty-emoji">
              <RoutineIcon size={44} />
            </div>
            <h2>{t("routine.empty.title")}</h2>
            <p>{t("routine.empty.body")}</p>
          </div>
        )
      ) : (
        dashboard && (
          <Dashboard dashboard={dashboard} onRemove={handleRemove} />
        )
      )}
    </div>
  );
}

// --- the dashboard ----------------------------------------------------------

function Dashboard({
  dashboard,
  onRemove,
}: {
  dashboard: RoutineDashboard;
  onRemove: (productId: string) => void;
}) {
  const { t, lang } = useI18n();
  const { products, goals, leaf_score } = dashboard;
  const am = products.filter((p) => p.timing === "AM" || p.timing === "AM & PM");
  const pm = products.filter((p) => p.timing === "PM" || p.timing === "AM & PM");
  const total = formatMonthlyTotal(lang, dashboard);

  return (
    <>
      {/* Product list + monthly cost */}
      <section className="dash-overview">
        <div className="card product-strip-card">
          <h2 className="card-title">
            {t("routine.products", { count: products.length })}
          </h2>
          <ul className="product-strip">
            {products.map((p) => (
              <li key={p.product_id} className="product-strip-row">
                <div className="product-strip-name">
                  <span className="product-brand">{p.brand}</span>
                  <span className="product-name">{p.product_name}</span>
                </div>
                <span className="product-strip-price">
                  {formatProductPrice(lang, p)}
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => onRemove(p.product_id)}
                  aria-label={`${t("routine.remove")} ${p.product_name}`}
                >
                  {t("routine.remove")}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card cost-card">
          <h2 className="card-title">{t("routine.monthlyCost")}</h2>
          {total != null ? (
            <>
              <div className="cost-value">≈ {total}</div>
              <div className="cost-unit">{t("routine.monthlyCost.unit")}</div>
              <p className="muted cost-note">{t("routine.monthlyCost.note")}</p>
            </>
          ) : (
            <p className="muted">{t("routine.monthlyCost.empty")}</p>
          )}
        </div>
      </section>

      {/* AM / PM columns */}
      <section className="routine-columns">
        <RoutineColumn title={t("routine.am")} icon={<SunIcon />} products={am} />
        <RoutineColumn title={t("routine.pm")} icon={<MoonIcon />} products={pm} />
      </section>

      {/* Goals + leaf score */}
      <GoalsCard goals={goals} leafScore={leaf_score} />
    </>
  );
}

function RoutineColumn({
  title,
  icon,
  products,
}: {
  title: string;
  icon: React.ReactNode;
  products: RoutineDashboardCard[];
}) {
  const { t } = useI18n();
  return (
    <div className="card routine-column">
      <div className="routine-column-head">
        {icon}
        <h2 className="card-title">{title}</h2>
      </div>
      {products.length === 0 ? (
        <p className="muted">{t("routine.noProductsTime")}</p>
      ) : (
        <ol className="routine-steps">
          {products.map((p) => (
            <li key={p.product_id} className="routine-step">
              <div className="routine-step-head">
                <span className="product-name">{p.product_name}</span>
                <span className="product-brand">{p.brand}</span>
              </div>
              {p.application_notes.length > 0 ? (
                <ul className="application-notes">
                  {p.application_notes.map((note, i) => (
                    <li key={i} className="application-note">
                      {note}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted application-note-empty">
                  {t("routine.noNotes")}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function GoalsCard({
  goals,
  leafScore,
}: {
  goals: RoutineDashboard["goals"];
  leafScore: number;
}) {
  const { t, term } = useI18n();
  return (
    <section className="card goals-card">
      <div className="card-title-row">
        <h2 className="card-title">{t("routine.goalsTitle")}</h2>
        <LeafScore score={leafScore} />
      </div>
      {goals.length === 0 ? (
        <p className="muted">{t("routine.goals.empty")}</p>
      ) : (
        <ul className="goal-list">
          {goals.map((g) => (
            <li key={g.goal} className={`goal-row goal-${coverageClass(g.covered)}`}>
              <span className="goal-mark" aria-hidden="true">
                {g.covered === true ? "✓" : g.covered === false ? "○" : "—"}
              </span>
              <span className="goal-name">{term(g.goal)}</span>
              <span className="goal-addressed">
                {g.addressed_by.length > 0
                  ? g.addressed_by.join(", ")
                  : g.covered === null
                    ? t("routine.goal.notAssessed")
                    : t("routine.goal.notCovered")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- add-product panel (scanner, with a manual fallback) --------------------

function AddProductPanel({
  userId,
  onChanged,
  onClose,
}: {
  userId: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);
  // Streaming state: real pipeline step (1..5) and the coach card as it types in.
  const [pipelineStep, setPipelineStep] = useState(1);
  const inputRef = useRef<HTMLInputElement>(null);
  const { currentUser } = useUsers();
  const { t } = useI18n();

  function chooseFile(f: File | null) {
    if (!f) return;
    if (!f.type.startsWith("image/")) {
      setError("Please choose an image file.");
      return;
    }
    setError(null);
    setResult(null);
    setPipelineStep(1);
    setFile(f);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
  }

  function resetScan() {
    setFile(null);
    setResult(null);
    setError(null);
    setPipelineStep(1);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleScan() {
    if (!file) return;
    setScanning(true);
    setError(null);
    setResult(null);
    setPipelineStep(1);
    try {
      const res = await api.scanStream(
        { image: file, userId, addToRoutine: true },
        {
          onStage: (step) => setPipelineStep((prev) => Math.max(prev, step)),
        },
      );
      setResult(res);
      if (res.added_product_id) onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setScanning(false);
    }
  }

  return (
    <section className="card add-panel">
      <div className="card-title-row">
        <h2 className="card-title">{t("routine.addPanel.title")}</h2>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>

      {!showManual ? (
        <>
          <div
            className={`dropzone${dragging ? " dragging" : ""}${
              preview ? " has-image" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              chooseFile(e.dataTransfer.files?.[0] ?? null);
            }}
            onClick={() => inputRef.current?.click()}
          >
            {preview ? (
              <img src={preview} alt="Label preview" className="preview-img" />
            ) : (
              <div className="dropzone-prompt">
                <div className="empty-emoji">
                  <CameraIcon size={46} />
                </div>
                <p>
                  <strong>{t("dropzone.drop")}</strong>
                  {t("dropzone.browse")}
                </p>
                <p className="muted">{t("dropzone.hint")}</p>
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {error && <div className="banner banner-error">{error}</div>}

          {file && !scanning && !result && (
            <div className="scan-controls-actions">
              <button className="btn btn-ghost" onClick={resetScan}>
                {t("common.clear")}
              </button>
              <button className="btn btn-primary" onClick={() => void handleScan()}>
                {t("routine.scanAndAdd")}
              </button>
            </div>
          )}

          {scanning && (
            <PipelineSteps
              userName={currentUser?.name ?? undefined}
              activeStep={pipelineStep}
            />
          )}

          {result && !scanning && (
            <>
              <ScanResult result={result} />
              <div className="scan-controls-actions">
                <button className="btn btn-ghost" onClick={resetScan}>
                  {t("routine.scanAnother")}
                </button>
                <button className="btn btn-primary" onClick={onClose}>
                  {t("common.done")}
                </button>
              </div>
            </>
          )}

          <button
            className="link-button manual-link"
            onClick={() => setShowManual(true)}
          >
            {t("routine.manualLink")}
          </button>
        </>
      ) : (
        <ManualAddForm
          userId={userId}
          onChanged={onChanged}
          onClose={onClose}
          onBack={() => setShowManual(false)}
        />
      )}
    </section>
  );
}

function ManualAddForm({
  userId,
  onChanged,
  onClose,
  onBack,
}: {
  userId: string;
  onChanged: () => void;
  onClose: () => void;
  onBack: () => void;
}) {
  const [brand, setBrand] = useState("");
  const [productName, setProductName] = useState("");
  const [ingredients, setIngredients] = useState<string[]>([]);
  const [isQuasiDrug, setIsQuasiDrug] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  async function handleAdd() {
    if (!brand.trim() || !productName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.addRoutineProduct(userId, {
        brand: brand.trim(),
        product_name: productName.trim(),
        ingredients,
        is_quasi_drug: isQuasiDrug,
      });
      onChanged();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {error && <div className="banner banner-error">{error}</div>}
      <div className="form-grid">
        <label className="field">
          <span className="field-label">{t("routine.manual.brand")}</span>
          <input
            className="text-input"
            value={brand}
            autoFocus
            onChange={(e) => setBrand(e.target.value)}
            placeholder={t("routine.manual.brand.placeholder")}
          />
        </label>
        <label className="field">
          <span className="field-label">{t("routine.manual.product")}</span>
          <input
            className="text-input"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder={t("routine.manual.product.placeholder")}
          />
        </label>
      </div>

      <label className="field">
        <span className="field-label">{t("routine.manual.ingredients")}</span>
        <TagInput
          values={ingredients}
          onChange={setIngredients}
          placeholder={t("routine.manual.ingredients.placeholder")}
        />
      </label>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={isQuasiDrug}
          onChange={(e) => setIsQuasiDrug(e.target.checked)}
        />
        <span>{t("routine.manual.quasiDrug")}</span>
      </label>

      <div className="page-actions-right">
        <button className="btn btn-ghost" onClick={onBack}>
          {t("routine.manual.back")}
        </button>
        <button
          className="btn btn-primary"
          onClick={() => void handleAdd()}
          disabled={saving || !brand.trim() || !productName.trim()}
        >
          {saving ? t("routine.manual.adding") : t("routine.manual.add")}
        </button>
      </div>
    </>
  );
}

// --- helpers + icons --------------------------------------------------------

function coverageClass(covered: boolean | null): string {
  if (covered === true) return "covered";
  if (covered === false) return "uncovered";
  return "unknown";
}

function SunIcon() {
  return (
    <svg
      className="time-icon sun"
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="24" cy="24" r="8" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => {
        const r = (deg * Math.PI) / 180;
        const x1 = 24 + Math.cos(r) * 14;
        const y1 = 24 + Math.sin(r) * 14;
        const x2 = 24 + Math.cos(r) * 19;
        const y2 = 24 + Math.sin(r) * 19;
        return <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} />;
      })}
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      className="time-icon moon"
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M30 8a16 16 0 1 0 10 28A18 18 0 0 1 30 8z" />
    </svg>
  );
}
