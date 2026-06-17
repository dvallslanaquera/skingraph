// Shared empty-state shown on pages that require an active user.
// `action` is the already-localised verb phrase (e.g. "manage a routine").
import { useI18n } from "../i18n";

export function NoUser({ action }: { action: string }) {
  const { t } = useI18n();
  return (
    <div className="empty-state">
      <div className="empty-emoji">👤</div>
      <h2>{t("noUser.title")}</h2>
      <p>{t("noUser.body", { action })}</p>
    </div>
  );
}
