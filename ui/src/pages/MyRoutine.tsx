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
import { LeafScore } from "../components/LeafScore";
import { NoUser } from "../components/NoUser";
import { PipelineSteps } from "../components/PipelineSteps";
import { ScanResult } from "../components/ScanResult";
import { TagInput } from "../components/TagInput";
import { useUsers } from "../context/UserContext";
import { prettify } from "../lib/profile";

export function MyRoutine() {
  const { currentUserId } = useUsers();

  const [dashboard, setDashboard] = useState<RoutineDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async (userId: string) => {
    setLoading(true);
    setError(null);
    try {
      setDashboard(await api.getRoutineDashboard(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentUserId) void load(currentUserId);
    else setDashboard(null);
  }, [currentUserId, load]);

  if (!currentUserId) return <NoUser action="manage a routine" />;

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
          <h1>My Routine</h1>
          <p className="page-sub">
            Scan a product to add it. New scans are also checked against your
            shelf for conflicts and redundancy.
          </p>
        </div>
        {!adding && (
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            + Add product
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
        <div className="card">Loading routine…</div>
      ) : products.length === 0 ? (
        !adding && (
          <div className="empty-state">
            <div className="empty-emoji">🧴</div>
            <h2>Your shelf is empty</h2>
            <p>Scan a product with “+ Add product” to build your routine.</p>
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
  const { products, monthly_cost_usd, goals, leaf_score } = dashboard;
  const am = products.filter((p) => p.timing === "AM" || p.timing === "AM & PM");
  const pm = products.filter((p) => p.timing === "PM" || p.timing === "AM & PM");

  return (
    <>
      {/* Product list + monthly cost */}
      <section className="dash-overview">
        <div className="card product-strip-card">
          <h2 className="card-title">Products ({products.length})</h2>
          <ul className="product-strip">
            {products.map((p) => (
              <li key={p.product_id} className="product-strip-row">
                <div className="product-strip-name">
                  <span className="product-brand">{p.brand}</span>
                  <span className="product-name">{p.product_name}</span>
                </div>
                <span className="product-strip-price">{priceLabel(p)}</span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => onRemove(p.product_id)}
                  aria-label={`Remove ${p.product_name}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card cost-card">
          <h2 className="card-title">Monthly cost</h2>
          {monthly_cost_usd != null ? (
            <>
              <div className="cost-value">≈ ${monthly_cost_usd.toFixed(2)}</div>
              <div className="cost-unit">/ month</div>
              <p className="muted cost-note">
                Amortized across your routine (price ÷ months a unit lasts), in
                USD. Looked up for the Japanese market where available.
              </p>
            </>
          ) : (
            <p className="muted">
              No prices yet — scan a product and we'll look up its cost.
            </p>
          )}
        </div>
      </section>

      {/* AM / PM columns */}
      <section className="routine-columns">
        <RoutineColumn title="AM routine" icon={<SunIcon />} products={am} />
        <RoutineColumn title="PM routine" icon={<MoonIcon />} products={pm} />
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
  return (
    <div className="card routine-column">
      <div className="routine-column-head">
        {icon}
        <h2 className="card-title">{title}</h2>
      </div>
      {products.length === 0 ? (
        <p className="muted">No products for this time of day yet.</p>
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
                  No special application notes.
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
  return (
    <section className="card goals-card">
      <div className="card-title-row">
        <h2 className="card-title">Goals &amp; routine score</h2>
        <LeafScore score={leafScore} />
      </div>
      {goals.length === 0 ? (
        <p className="muted">
          Add goals on My Profile to see how well your routine covers them.
        </p>
      ) : (
        <ul className="goal-list">
          {goals.map((g) => (
            <li key={g.goal} className={`goal-row goal-${coverageClass(g.covered)}`}>
              <span className="goal-mark" aria-hidden="true">
                {g.covered === true ? "✓" : g.covered === false ? "○" : "—"}
              </span>
              <span className="goal-name">{prettify(g.goal)}</span>
              <span className="goal-addressed">
                {g.addressed_by.length > 0
                  ? g.addressed_by.join(", ")
                  : g.covered === null
                    ? "not assessed"
                    : "not yet covered"}
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
  const inputRef = useRef<HTMLInputElement>(null);
  const { currentUser } = useUsers();

  function chooseFile(f: File | null) {
    if (!f) return;
    if (!f.type.startsWith("image/")) {
      setError("Please choose an image file.");
      return;
    }
    setError(null);
    setResult(null);
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
    try {
      const res = await api.scan({ image: file, userId, addToRoutine: true });
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
        <h2 className="card-title">Add a product</h2>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          Close
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
                <div className="empty-emoji">📷</div>
                <p>
                  <strong>Drop a label photo here</strong> or click to browse
                </p>
                <p className="muted">Front or back of the product. Max 15 MB.</p>
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
                Clear
              </button>
              <button className="btn btn-primary" onClick={() => void handleScan()}>
                Scan &amp; add
              </button>
            </div>
          )}

          {scanning && <PipelineSteps userName={currentUser?.name ?? undefined} />}

          {result && !scanning && (
            <>
              <ScanResult result={result} />
              <div className="scan-controls-actions">
                <button className="btn btn-ghost" onClick={resetScan}>
                  Scan another
                </button>
                <button className="btn btn-primary" onClick={onClose}>
                  Done
                </button>
              </div>
            </>
          )}

          <button
            className="link-button manual-link"
            onClick={() => setShowManual(true)}
          >
            Can't scan it? Enter manually
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
          <span className="field-label">Brand</span>
          <input
            className="text-input"
            value={brand}
            autoFocus
            onChange={(e) => setBrand(e.target.value)}
            placeholder="e.g. Hada Labo"
          />
        </label>
        <label className="field">
          <span className="field-label">Product name</span>
          <input
            className="text-input"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="e.g. Gokujyun Lotion"
          />
        </label>
      </div>

      <label className="field">
        <span className="field-label">Ingredients (canonical INCI names)</span>
        <TagInput
          values={ingredients}
          onChange={setIngredients}
          placeholder="e.g. Sodium Hyaluronate"
        />
      </label>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={isQuasiDrug}
          onChange={(e) => setIsQuasiDrug(e.target.checked)}
        />
        <span>Quasi-drug (医薬部外品)</span>
      </label>

      <div className="page-actions-right">
        <button className="btn btn-ghost" onClick={onBack}>
          ← Back to scan
        </button>
        <button
          className="btn btn-primary"
          onClick={() => void handleAdd()}
          disabled={saving || !brand.trim() || !productName.trim()}
        >
          {saving ? "Adding…" : "Add to routine"}
        </button>
      </div>
    </>
  );
}

// --- helpers + icons --------------------------------------------------------

function priceLabel(p: RoutineDashboardCard): string {
  if (p.monthly_cost_usd != null) return `≈ $${p.monthly_cost_usd.toFixed(2)}/mo`;
  if (p.price_usd != null) return `$${p.price_usd.toFixed(2)}`;
  return "—";
}

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
