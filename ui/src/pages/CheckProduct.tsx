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

export function CheckProduct() {
  const { currentUserId, currentUser } = useUsers();

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [addToRoutine, setAddToRoutine] = useState(false);
  const [dragging, setDragging] = useState(false);

  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const res = await api.scan({
        image: file,
        userId: currentUserId ?? undefined,
        addToRoutine: addToRoutine && !!currentUserId,
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

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Check Product</h1>
          <p className="page-sub">
            {currentUser
              ? `Personalised for ${currentUser.name || currentUser.user_id}.`
              : "Scanning anonymously — pick a user for personalised advice."}
          </p>
        </div>
      </header>

      <section className="card">
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
            hidden
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="upload-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => cameraInputRef.current?.click()}
          >
            📷 Take a photo
          </button>
          <span className="muted upload-actions-hint">
            Use your phone camera, or drop / browse for an existing photo above.
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
            <label
              className={`checkbox-row${!currentUserId ? " disabled" : ""}`}
            >
              <input
                type="checkbox"
                checked={addToRoutine && !!currentUserId}
                disabled={!currentUserId}
                onChange={(e) => setAddToRoutine(e.target.checked)}
              />
              <span>
                Save to my routine
                {!currentUserId && " (select a user first)"}
              </span>
            </label>

            <div className="scan-controls-actions">
              <button
                className="btn btn-ghost"
                onClick={reset}
                disabled={scanning}
              >
                Clear
              </button>
              <button
                className="btn btn-primary"
                onClick={() => void handleScan()}
                disabled={scanning}
              >
                {scanning ? "Scanning…" : "Scan product"}
              </button>
            </div>
          </div>
        )}
      </section>

      {error && <div className="banner banner-error">{error}</div>}

      {scanning && (
        <PipelineSteps userName={currentUser?.name ?? undefined} />
      )}

      {result && !scanning && <ScanResult result={result} />}
    </div>
  );
}
