// "My Routine" — the user's saved "shelf" of products.
//
// Lists /users/{id}/routine, lets you add a product manually (brand, name,
// INCI ingredients) and remove existing ones. Scans can also push products here
// from the Check Product page.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { RoutineProduct } from "../api/types";
import { NoUser } from "../components/NoUser";
import { TagInput } from "../components/TagInput";
import { useUsers } from "../context/UserContext";

export function MyRoutine() {
  const { currentUserId } = useUsers();

  const [products, setProducts] = useState<RoutineProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [brand, setBrand] = useState("");
  const [productName, setProductName] = useState("");
  const [ingredients, setIngredients] = useState<string[]>([]);
  const [isQuasiDrug, setIsQuasiDrug] = useState(false);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async (userId: string) => {
    setLoading(true);
    setError(null);
    try {
      setProducts(await api.getRoutine(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentUserId) void load(currentUserId);
    else setProducts([]);
  }, [currentUserId, load]);

  if (!currentUserId) return <NoUser action="manage a routine" />;

  function resetForm() {
    setBrand("");
    setProductName("");
    setIngredients([]);
    setIsQuasiDrug(false);
    setShowForm(false);
  }

  async function handleAdd() {
    if (!currentUserId || !brand.trim() || !productName.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await api.addRoutineProduct(currentUserId, {
        brand: brand.trim(),
        product_name: productName.trim(),
        ingredients,
        is_quasi_drug: isQuasiDrug,
      });
      resetForm();
      await load(currentUserId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAdding(false);
    }
  }

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

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>My Routine</h1>
          <p className="page-sub">
            Products on your shelf. New scans are checked against these for
            conflicts and redundancy.
          </p>
        </div>
        {!showForm && (
          <button
            className="btn btn-primary"
            onClick={() => setShowForm(true)}
          >
            + Add product
          </button>
        )}
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {showForm && (
        <section className="card">
          <h2 className="card-title">Add a product</h2>
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
            <span className="field-label">
              Ingredients (canonical INCI names)
            </span>
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
            <button className="btn btn-ghost" onClick={resetForm}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={() => void handleAdd()}
              disabled={adding || !brand.trim() || !productName.trim()}
            >
              {adding ? "Adding…" : "Add to routine"}
            </button>
          </div>
        </section>
      )}

      {loading ? (
        <div className="card">Loading routine…</div>
      ) : products.length === 0 ? (
        <div className="empty-state">
          <div className="empty-emoji">🧴</div>
          <h2>Your shelf is empty</h2>
          <p>Add a product above, or scan one from Check Product.</p>
        </div>
      ) : (
        <div className="routine-grid">
          {products.map((p) => (
            <article key={p.product_id} className="product-card">
              <div className="product-card-head">
                <div>
                  <div className="product-brand">{p.brand}</div>
                  <div className="product-name">{p.product_name}</div>
                </div>
                {p.is_quasi_drug && (
                  <span className="badge badge-quasi">医薬部外品</span>
                )}
              </div>

              {p.ingredients.length > 0 ? (
                <div className="ingredient-chips">
                  {p.ingredients.map((ing) => (
                    <span key={ing} className="ingredient-chip">
                      {ing}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="muted">No ingredients recorded.</p>
              )}

              <button
                className="btn btn-ghost btn-sm product-remove"
                onClick={() => void handleRemove(p.product_id)}
              >
                Remove
              </button>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
