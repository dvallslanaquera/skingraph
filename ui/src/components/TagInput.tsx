// Editable list of string "chips" with optional click-to-add suggestions.
// Used for profile goals / skin conditions and for routine ingredient lists.
import { useState } from "react";

interface TagInputProps {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  // Maps a stored value to its display label (values stay canonical on save).
  formatLabel?: (value: string) => string;
}

export function TagInput({
  values,
  onChange,
  placeholder = "Type and press Enter",
  suggestions = [],
  formatLabel = (v) => v,
}: TagInputProps) {
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const value = raw.trim();
    if (!value || values.includes(value)) return;
    onChange([...values, value]);
    setDraft("");
  }

  function remove(value: string) {
    onChange(values.filter((v) => v !== value));
  }

  const unusedSuggestions = suggestions.filter((s) => !values.includes(s));

  return (
    <div className="tag-input">
      <div className="tag-list">
        {values.map((v) => (
          <span key={v} className="tag">
            {formatLabel(v)}
            <button
              type="button"
              className="tag-remove"
              aria-label={`Remove ${formatLabel(v)}`}
              onClick={() => remove(v)}
            >
              ×
            </button>
          </span>
        ))}
        <input
          className="tag-field"
          value={draft}
          placeholder={values.length === 0 ? placeholder : ""}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && values.length) {
              remove(values[values.length - 1]);
            }
          }}
        />
      </div>

      {unusedSuggestions.length > 0 && (
        <div className="tag-suggestions">
          {unusedSuggestions.map((s) => (
            <button
              key={s}
              type="button"
              className="chip-suggestion"
              onClick={() => add(s)}
            >
              + {formatLabel(s)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
