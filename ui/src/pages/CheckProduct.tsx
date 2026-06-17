// "Check Product" — upload a label photo, run the scan pipeline, show advice.
//
// Works with or without a selected user; when a user is active the scan is
// personalised and can optionally be saved to their routine.
import { useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ScanResponse } from "../api/types";
import { PipelineSteps } from "../components/PipelineSteps";
import { ScanResult } from "../components/ScanResult";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";

export function CheckProduct() {
  const { t } = useI18n();
  const { currentUserId, currentUser } = useUsers();

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Post-scan "save to my routine" (manual-add path), shown once a scan lands.
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Two inputs: a plain file picker (drag/drop + gallery) and a camera input
  // (capture="environment") so phone users can shoot the label directly.
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  function chooseFile(f: File | null) {
    if (!f) return;
    if (!f.type.startsWith("image/")) {
      setError("Please choose an image file.");
      return;
    }
    setError(null);
    setResult(null);
    setSavedId(null);
    setSaveError(null);
    setFile(f);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
    setSavedId(null);
    setSaveError(null);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    if (inputRef.current) inputRef.current.value = "";
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  }

  async function handleScan() {
    if (!file) return;
    setScanning(true);
    setError(null);
    setResult(null);
    setSavedId(null);
    setSaveError(null);
    try {
      const res = await api.scan({
        image: file,
        userId: currentUserId ?? undefined,
      });
      setResult(res);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e),
      );
    } finally {
      setScanning(false);
    }
  }

  async function saveToRoutine() {
    if (!currentUserId || !result?.product) return;
    // Prefer canonical INCI names from the normalizer; fall back to the raw
    // extracted names so the saved product is never left without ingredients.
    const inci = result.standardized_ingredients
      .map((i) => i.name_standardized)
      .filter((n): n is string => !!n);
    const ingredients = inci.length
      ? inci
      : result.product.ingredients.map((i) => i.name_standardized || i.name_raw);

    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.addRoutineProduct(currentUserId, {
        brand: result.product.brand,
        product_name: result.product.product_name,
        ingredients,
        is_quasi_drug: result.product.is_quasi_drug ?? undefined,
      });
      setSavedId(res.product_id);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t("check.title")}</h1>
          <p className="page-sub">
            {currentUser
              ? t("check.sub.personalised", {
                  name: currentUser.name || currentUser.user_id,
                })
              : t("check.sub.anon")}
          </p>
        </div>
      </header>

      <section className="card">
        <div
          className={`dropzone${dragging ? " dragging" : ""}${
            preview ? " has-image" : ""
          }${scanning ? " scanning" : ""}`}
          onDragOver={(e) => {
            if (scanning) return;
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            if (scanning) return;
            e.preventDefault();
            setDragging(false);
            chooseFile(e.dataTransfer.files?.[0] ?? null);
          }}
          onClick={() => {
            if (!scanning) inputRef.current?.click();
          }}
        >
          {preview ? (
            <img src={preview} alt="Label preview" className="preview-img" />
          ) : (
            <div className="dropzone-prompt">
              <div className="empty-emoji">📷</div>
              <p>
                <strong>{t("dropzone.drop")}</strong>
                {t("dropzone.browse")}
              </p>
              <p className="muted">{t("dropzone.hint")}</p>
            </div>
          )}
          {scanning && (
            <div className="scan-overlay" aria-label="Processing image">
              <span className="spinner" />
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="upload-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => cameraInputRef.current?.click()}
            disabled={scanning}
          >
            {t("check.takePhoto")}
          </button>
          <span className="muted upload-actions-hint">
            {t("check.uploadHint")}
          </span>
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {file && (
          <div className="scan-controls">
            <div className="scan-controls-actions">
              <button
                className="btn btn-ghost"
                onClick={reset}
                disabled={scanning}
              >
                {t("common.clear")}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => void handleScan()}
                disabled={scanning}
              >
                {scanning ? t("check.scanning") : t("check.scan")}
              </button>
            </div>
          </div>
        )}
      </section>

      {error && <div className="banner banner-error">{error}</div>}

      {scanning && (
        <PipelineSteps userName={currentUser?.name ?? undefined} />
      )}

      {result && !scanning && (
        <>
          <ScanResult result={result} />

          {result.product && (
            <section className="card save-routine-card">
              {savedId ? (
                <div className="banner banner-ok">{t("check.save.saved")}</div>
              ) : currentUserId ? (
                <>
                  {saveError && (
                    <div className="banner banner-error">{saveError}</div>
                  )}
                  <div className="save-routine-row">
                    <span>{t("check.save.prompt")}</span>
                    <button
                      className="btn btn-primary"
                      onClick={() => void saveToRoutine()}
                      disabled={saving}
                    >
                      {saving ? t("common.saving") : t("check.save.button")}
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted">{t("check.save.selectUser")}</p>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
