// "Check Product" — upload a label photo, run the scan pipeline, show advice.
//
// Works with or without a selected user; when a user is active the scan is
// personalised and can optionally be saved to their routine.
import { useEffect, useRef, useState } from "react";
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

  // Streaming state: the real pipeline step (1..5) driving the progress list.
  const [pipelineStep, setPipelineStep] = useState(1);

  // Post-scan "save to my routine" (manual-add path), shown once a scan lands.
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Two inputs: a plain file picker (drag/drop + gallery) and a camera input
  // (capture="environment") so phone users can shoot the label directly.
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  // Bring the live progress list into view when a scan starts — on phones the
  // dropzone fills the screen and the 分析中 steps would sit below the fold.
  const stepsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scanning) {
      stepsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [scanning]);

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
    setPipelineStep(1);
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
    setPipelineStep(1);
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
    setPipelineStep(1);
    try {
      const res = await api.scanStream(
        {
          image: file,
          userId: currentUserId ?? undefined,
        },
        {
          onStage: (step) => setPipelineStep((prev) => Math.max(prev, step)),
        },
      );
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
          <p className="page-eyebrow">{t("check.eyebrow")}</p>
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

      <section className="check-hero" aria-label="Upload label">
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

        {/* the coach, peeking from beside the upload card */}
        <aside className="check-coach">
          <svg
            className="cat-peek"
            viewBox="0 0 120 120"
            fill="none"
            aria-hidden="true"
          >
            {/* ears */}
            <path
              d="M34 52 28 28 52 42Z"
              fill="#fff"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <path
              d="M86 52 92 28 68 42Z"
              fill="#fff"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <path d="M35 46 33 36 44 42Z" fill="#fceae6" />
            <path d="M85 46 87 36 76 42Z" fill="#fceae6" />
            {/* head */}
            <path
              d="M60 38c18 0 30 14 30 31 0 18-13 30-30 30S30 87 30 69c0-17 12-31 30-31Z"
              fill="#fff"
              stroke="currentColor"
              strokeWidth="3"
            />
            {/* calm closed eyes */}
            <path
              className="eye"
              d="M44 66c2.5 3 6.5 3 9 0"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
            />
            <path
              className="eye"
              d="M67 66c2.5 3 6.5 3 9 0"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
            />
            {/* nose + mouth */}
            <path d="M56 75h8l-4 4Z" fill="#ee9e92" />
            <path
              d="M60 79c-1.5 3-5 3-6.5 1M60 79c1.5 3 5 3 6.5 1"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
            />
            {/* whiskers */}
            <path
              d="M40 72 22 69M41 78 24 80M80 72 98 69M79 78 96 80"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.7"
            />
          </svg>

          <div className="coach-quote">
            <p>{t("check.coachLine")}</p>
            <span className="coach-by">
              <span className="cat-chip" aria-hidden="true">
                <svg viewBox="0 0 120 120" fill="none">
                  <path d="M34 52 28 30 50 43Z" fill="currentColor" />
                  <path d="M86 52 92 30 70 43Z" fill="currentColor" />
                  <path
                    d="M60 40c17 0 28 13 28 29s-12 28-28 28-28-12-28-28 11-29 28-29Z"
                    fill="currentColor"
                  />
                  <path
                    d="M48 66c2 2.5 6 2.5 8 0M64 66c2 2.5 6 2.5 8 0"
                    stroke="#fff"
                    strokeWidth="3"
                    strokeLinecap="round"
                  />
                  <path d="M57 75h6l-3 3Z" fill="#fff" />
                </svg>
              </span>
              {t("check.coachBy")}
            </span>
          </div>
        </aside>
      </section>

      <div className="upload-actions">
        <button
          type="button"
          className="btn btn-primary btn-photo"
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

      {error && <div className="banner banner-error">{error}</div>}

      {scanning && (
        <div ref={stepsRef}>
          <PipelineSteps
            userName={currentUser?.name ?? undefined}
            activeStep={pipelineStep}
          />
        </div>
      )}

      {result && !scanning && (
        <>
          <ScanResult result={result} />

          {!currentUserId && result.status === "complete" && (
            <div className="banner banner-nudge">
              <span>{t("check.nudge.text")}</span>
              <a href="#profile" className="nudge-link">
                {t("check.nudge.link")}
              </a>
            </div>
          )}

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
