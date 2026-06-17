// Language context: holds the active UI language (default Japanese, persisted to
// localStorage) and exposes a translate helper `t` plus `term` for localising
// stored canonical values. Wrap the app in <LanguageProvider>.
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { type Lang, STRINGS, localizeTerm } from "./strings";

export type { Lang } from "./strings";

const STORAGE_KEY = "skingraph.lang";
const DEFAULT_LANG: Lang = "ja";

interface I18nValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  term: (value: string) => string;
}

const I18nContext = createContext<I18nValue | undefined>(undefined);

function interpolate(
  template: string,
  vars?: Record<string, string | number>,
): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "ja" || saved === "en" ? saved : DEFAULT_LANG;
  });

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => interpolate(STRINGS[lang][key] ?? key, vars),
      term: (v) => localizeTerm(lang, v),
    }),
    [lang, setLang],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within a LanguageProvider");
  return ctx;
}
