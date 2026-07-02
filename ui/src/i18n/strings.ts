// Translation dictionary + value/term localisation for the EN / JA UI.
//
// STRINGS holds UI-chrome copy keyed by dotted ids (identical keys per language).
// TERMS_JA maps canonical stored values (English, lowercase) to Japanese labels;
// English just uses prettify(). Prices: the JA view shows yen (native JPY from
// the price lookup for products; a fixed display rate for the USD-based budget).
import { prettify } from "../lib/profile";

export type Lang = "ja" | "en";

export const LANGS: Lang[] = ["ja", "en"];

// Display-only USD→JPY rate, used for the budget slider (a USD preference with no
// "native" price to read). Product prices use real native JPY from the lookup.
export const BUDGET_USD_TO_JPY = 150;

export const STRINGS: Record<Lang, Record<string, string>> = {
  en: {
    "lang.name": "English",
    "brand.sub": "Skincare Coach",
    "nav.profile.label": "My Profile",
    "nav.profile.hint": "Your skin data",
    "nav.routine.label": "My Routine",
    "nav.routine.hint": "Products you use",
    "nav.check.label": "Check Product",
    "nav.check.hint": "Scan & get advice",

    "common.create": "Create",
    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.clear": "Clear",
    "common.done": "Done",
    "common.saving": "Saving…",
    "common.perMonthShort": "/mo",

    "userPicker.activeUser": "Active user",
    "userPicker.unreachable": "API unreachable",
    "userPicker.loading": "Loading…",
    "userPicker.select": "— select a user —",
    "userPicker.newName": "New user name",
    "userPicker.newUser": "+ New user",

    "noUser.title": "No user selected",
    "noUser.body": "Pick a user from the sidebar (or create one) to {action}.",
    "noUser.action.profile": "view and edit a profile",
    "noUser.action.routine": "manage a routine",

    "dropzone.drop": "Drop a label photo here",
    "dropzone.browse": " or click to browse",
    "dropzone.hint": "Front or back of the product. Max 15 MB.",

    "profile.title": "My Profile",
    "profile.sub": "This data personalises every scan's safety check and coaching — it's used only to tailor your advice.",
    "profile.loading": "Loading profile…",
    "profile.section.identity": "Identity",
    "profile.displayName": "Display name",
    "profile.displayName.placeholder": "e.g. Hana",
    "profile.age": "Age",
    "profile.age.help": "Skin thins and renews more slowly with age, so advice is tuned to your stage of life.",
    "profile.gender": "Gender",
    "profile.gender.help": "Skin thickness, oil and hormones differ between sexes, so this shapes what suits you.",
    "gender.male": "Male",
    "gender.female": "Female",
    "gender.other": "Prefer not to say",
    "routineTime.minimal.title": "Minimal / lazy",
    "routineTime.minimal.detail": "Under 5 min/day, once daily — for busy people short on time.",
    "routineTime.moderate.title": "Moderate",
    "routineTime.moderate.detail": "5–15 min/day, usually morning and night.",
    "routineTime.extensive.title": "Extensive / serious",
    "routineTime.extensive.detail": "No time limits — happy with a full multi-step routine.",
    "profile.pregnancy": "🤰 I'm pregnant — flag pregnancy-unsafe ingredients (e.g. retinoids)",
    "profile.section.skin": "Skin",
    "profile.fitz": "Fitzpatrick skin type",
    "profile.fitz.help": "Pick the swatch closest to your skin. Use the row that matches your undertone — at the same level, Asian and other skins differ.",
    "profile.fitz.asian": "Asian undertones",
    "profile.fitz.other": "Other undertones",
    "profile.skinType": "Skin type",
    "profile.skinType.help": "Dry, oily or sensitive skin tolerates very different actives and textures.",
    "profile.sunDamage": "Sun damage history",
    "profile.sunDamage.help": "Past sun exposure guides how cautiously to introduce stronger ingredients.",
    "profile.goals": "Goals",
    "profile.goals.placeholder": "e.g. fine lines",
    "profile.goals.help": "Your goals decide which ingredients the coach prioritises for you.",
    "profile.conditions": "Skin conditions",
    "profile.conditions.placeholder": "e.g. rosacea",
    "profile.conditions.help": "Conditions and illnesses can make some ingredients risky, so the coach keeps them in mind.",
    "profile.section.prefs": "Preferences",
    "profile.routineTime": "Routine time",
    "profile.routineTime.help": "How much time you'll spend decides how many steps the coach suggests.",
    "profile.devices": "Also consider devices / at-home treatments. When on, the coach may suggest tools like LED masks, at-home IPL, microneedle stamps or gua sha to enrich your routine.",
    "profile.budget": "Monthly budget",
    "profile.budget.help": "Your approximate monthly skincare spend. This affects which products the coach recommends.",
    "profile.budget.notSet": "Not set",
    "profile.delete": "Delete user",
    "profile.deleting": "Deleting…",
    "profile.deleteConfirm": "Delete this user and their routine? This cannot be undone.",
    "profile.save": "Save changes",
    "profile.saved": "✓ Saved",

    "routine.title": "My Routine",
    "routine.sub": "Scan a product to add it. New scans are also checked against your shelf for conflicts and redundancy.",
    "routine.addProduct": "+ Add product",
    "routine.loading": "Loading routine…",
    "routine.empty.title": "Your shelf is empty",
    "routine.empty.body": "Scan a product with “+ Add product” to build your routine.",
    "routine.products": "Products ({count})",
    "routine.remove": "Remove",
    "routine.monthlyCost": "Monthly cost",
    "routine.monthlyCost.unit": "/ month",
    "routine.monthlyCost.note": "Amortized across your routine (price ÷ months a unit lasts). Looked up for the Japanese market where available.",
    "routine.monthlyCost.empty": "No prices yet — scan a product and we'll look up its cost.",
    "routine.am": "AM routine",
    "routine.pm": "PM routine",
    "routine.noProductsTime": "No products for this time of day yet.",
    "routine.noNotes": "No special application notes.",
    "routine.goalsTitle": "Goals & routine score",
    "routine.goals.empty": "Add goals on My Profile to see how well your routine covers them.",
    "routine.goal.notAssessed": "not assessed",
    "routine.goal.notCovered": "not yet covered",
    "routine.addPanel.title": "Add a product",
    "routine.scanAndAdd": "Scan & add",
    "routine.scanAnother": "Scan another",
    "routine.manualLink": "Can't scan it? Enter manually",
    "routine.manual.brand": "Brand",
    "routine.manual.brand.placeholder": "e.g. Hada Labo",
    "routine.manual.product": "Product name",
    "routine.manual.product.placeholder": "e.g. Gokujyun Lotion",
    "routine.manual.ingredients": "Ingredients (canonical INCI names)",
    "routine.manual.ingredients.placeholder": "e.g. Sodium Hyaluronate",
    "routine.manual.quasiDrug": "Quasi-drug (医薬部外品)",
    "routine.manual.back": "← Back to scan",
    "routine.manual.add": "Add to routine",
    "routine.manual.adding": "Adding…",

    "check.title": "Check Product",
    "check.sub.personalised": "Personalised for {name}.",
    "check.sub.anon": "Scanning anonymously — pick a user for personalised advice.",
    "check.takePhoto": "📷 Take a photo",
    "check.uploadHint": "Use your phone camera, or drop / browse for an existing photo above.",
    "check.scan": "Scan product",
    "check.scanning": "Scanning…",
    "check.save.prompt": "Like this product? Add it to your shelf.",
    "check.save.button": "Save to my routine",
    "check.save.saved": "✓ Saved to your routine.",
    "check.save.selectUser": "Select a user to save this product to a routine.",

    "pipeline.title": "Analysing…",
    "pipeline.step1": "Scanning the picture…",
    "pipeline.step2": "Extracting ingredients…",
    "pipeline.step3": "Looking for dangerous ingredients…",
    "pipeline.step4": "Comparing to your routine…",
    "pipeline.step5": "Creating a recommendation for {name}…",
    "pipeline.note": "It can take up to 1 minute.",
    "pipeline.you": "you",

    "scan.status.complete.label": "Complete",
    "scan.status.complete.blurb": "A full recommendation was produced.",
    "scan.status.retake_required.label": "Retake needed",
    "scan.status.retake_required.blurb": "The label couldn't be read — try a sharper, well-lit photo.",
    "scan.status.action_needed.label": "Action needed",
    "scan.status.action_needed.blurb": "The product identity or ingredients need confirmation.",
    "scan.status.incomplete.label": "Incomplete",
    "scan.status.incomplete.blurb": "The pipeline exited without advice.",
    "scan.coachTitle": "Your coach says",
    "scan.recoLabel": "How recommendable for you",
    "scan.coach.timing": "Best time",
    "scan.coach.timing.AM": "Morning (AM)",
    "scan.coach.timing.PM": "Evening (PM)",
    "scan.coach.timing.AM & PM": "Morning & evening",
    "scan.coach.frequency": "How often",
    "scan.coach.warnings": "Watch out for",
    "scan.coach.howToApply": "How to apply",
    "scan.coach.fit": "Fitting it into your routine",
    "scan.meta.source": "Source",
    "scan.meta.ingredientsVia": "Ingredients via",
    "scan.meta.language": "Language",
    "scan.meta.confidence": "Confidence",
    "scan.safety": "Safety",
    "scan.safety.safe": "{pct} safe",
    "scan.safety.conflicts": "Conflicts",
    "scan.safety.flagged": "Flagged ingredients",
    "scan.safety.none": "No safety flags. 👍",
    "scan.fitTitle": "Fit with your routine",
    "scan.fit.conflicts": "Conflicts",
    "scan.fit.redundant": "Possibly redundant",
    "scan.fit.valueAdd": "Adds value for",
    "scan.ingredients": "Ingredients ({count})",
    "scan.unmatched": "Unmatched: {list}",
    "scan.sources": "Sources",
  },
  ja: {
    "lang.name": "日本語",
    "brand.sub": "スキンケアコーチ",
    "nav.profile.label": "プロフィール",
    "nav.profile.hint": "あなたの肌データ",
    "nav.routine.label": "マイルーティン",
    "nav.routine.hint": "使用中の製品",
    "nav.check.label": "製品チェック",
    "nav.check.hint": "スキャンしてアドバイス",

    "common.create": "作成",
    "common.cancel": "キャンセル",
    "common.close": "閉じる",
    "common.clear": "クリア",
    "common.done": "完了",
    "common.saving": "保存中…",
    "common.perMonthShort": "/月",

    "userPicker.activeUser": "現在のユーザー",
    "userPicker.unreachable": "APIに接続できません",
    "userPicker.loading": "読み込み中…",
    "userPicker.select": "— ユーザーを選択 —",
    "userPicker.newName": "新しいユーザー名",
    "userPicker.newUser": "+ 新規ユーザー",

    "noUser.title": "ユーザーが選択されていません",
    "noUser.body": "サイドバーからユーザーを選択（または作成）すると、{action}ことができます。",
    "noUser.action.profile": "プロフィールを表示・編集する",
    "noUser.action.routine": "ルーティンを管理する",

    "dropzone.drop": "成分表示の写真をここにドロップ",
    "dropzone.browse": " またはクリックして選択",
    "dropzone.hint": "製品の表面または裏面。最大15MB。",

    "profile.title": "プロフィール",
    "profile.sub": "このデータは、すべてのスキャンの安全チェックとアドバイスをあなた仕様にするためだけに使います。",
    "profile.loading": "プロフィールを読み込み中…",
    "profile.section.identity": "基本情報",
    "profile.displayName": "表示名",
    "profile.displayName.placeholder": "例：ハナ",
    "profile.age": "年齢",
    "profile.age.help": "年齢とともに肌は薄くなり、生まれ変わりもゆっくりに。年代に合わせて調整します。",
    "profile.gender": "性別",
    "profile.gender.help": "性別により肌の厚み・皮脂・ホルモンが異なるため、あなたに合うケアの参考にします。",
    "gender.male": "男性",
    "gender.female": "女性",
    "gender.other": "回答しない",
    "routineTime.minimal.title": "最小限 / ものぐさ",
    "routineTime.minimal.detail": "1日5分以内・1回だけ — 忙しくて時間がない人向け。",
    "routineTime.moderate.title": "標準",
    "routineTime.moderate.detail": "1日5〜15分・朝と夜が中心。",
    "routineTime.extensive.title": "本格的 / こだわり",
    "routineTime.extensive.detail": "時間制限なし — 多ステップのフルルーティンもOK。",
    "profile.pregnancy": "🤰 妊娠中です — 妊娠中に注意が必要な成分（レチノイドなど）を警告する",
    "profile.section.skin": "肌",
    "profile.fitz": "フィッツパトリック スキンタイプ",
    "profile.fitz.help": "ご自身の肌に最も近い色を選んでください。肌の色味に合った行を使います — 同じレベルでも、アジア系とその他の肌では色味が異なります。",
    "profile.fitz.asian": "アジア系の肌色",
    "profile.fitz.other": "その他の肌色",
    "profile.skinType": "肌タイプ",
    "profile.skinType.help": "乾燥・脂性・敏感など、肌タイプで合う成分やテクスチャーが変わります。",
    "profile.sunDamage": "日焼けダメージ歴",
    "profile.sunDamage.help": "過去の日焼けの程度に応じて、強い成分の取り入れ方を調整します。",
    "profile.goals": "目標",
    "profile.goals.placeholder": "例：小じわ",
    "profile.goals.help": "あなたの目標に合わせて、コーチが優先する成分を選びます。",
    "profile.conditions": "肌の悩み・症状",
    "profile.conditions.placeholder": "例：酒さ",
    "profile.conditions.help": "症状や持病によっては避けたい成分があるため、コーチが考慮します。",
    "profile.section.prefs": "設定",
    "profile.routineTime": "スキンケアにかける時間",
    "profile.routineTime.help": "かけられる時間に応じて、提案するステップ数を決めます。",
    "profile.devices": "美容機器・自宅ケアも考慮する。オンにすると、LEDマスク、自宅用IPL、マイクロニードルスタンプ、かっさなどのツールをコーチが提案することがあります。",
    "profile.budget": "月額予算",
    "profile.budget.help": "おおよその月のスキンケア費用です。コーチが提案する製品に影響します。",
    "profile.budget.notSet": "未設定",
    "profile.delete": "ユーザーを削除",
    "profile.deleting": "削除中…",
    "profile.deleteConfirm": "このユーザーとそのルーティンを削除しますか？この操作は取り消せません。",
    "profile.save": "変更を保存",
    "profile.saved": "✓ 保存しました",

    "routine.title": "マイルーティン",
    "routine.sub": "製品をスキャンして追加します。新しいスキャンは、棚の製品との競合や重複もチェックされます。",
    "routine.addProduct": "+ 製品を追加",
    "routine.loading": "ルーティンを読み込み中…",
    "routine.empty.title": "棚が空です",
    "routine.empty.body": "「+ 製品を追加」から製品をスキャンしてルーティンを作りましょう。",
    "routine.products": "製品（{count}）",
    "routine.remove": "削除",
    "routine.monthlyCost": "月額コスト",
    "routine.monthlyCost.unit": "/ 月",
    "routine.monthlyCost.note": "ルーティン全体で月割り（価格 ÷ 1個が持つ月数）。可能な場合は日本市場の価格を参照しています。",
    "routine.monthlyCost.empty": "まだ価格がありません — 製品をスキャンすると価格を調べます。",
    "routine.am": "朝のルーティン",
    "routine.pm": "夜のルーティン",
    "routine.noProductsTime": "この時間帯の製品はまだありません。",
    "routine.noNotes": "特別な使用上の注意はありません。",
    "routine.goalsTitle": "目標とルーティンスコア",
    "routine.goals.empty": "プロフィールで目標を追加すると、ルーティンがどれだけカバーしているか確認できます。",
    "routine.goal.notAssessed": "評価対象外",
    "routine.goal.notCovered": "まだカバーされていません",
    "routine.addPanel.title": "製品を追加",
    "routine.scanAndAdd": "スキャンして追加",
    "routine.scanAnother": "別の製品をスキャン",
    "routine.manualLink": "スキャンできない場合は手動で入力",
    "routine.manual.brand": "ブランド",
    "routine.manual.brand.placeholder": "例：肌ラボ",
    "routine.manual.product": "製品名",
    "routine.manual.product.placeholder": "例：極潤ローション",
    "routine.manual.ingredients": "成分（INCI名）",
    "routine.manual.ingredients.placeholder": "例：Sodium Hyaluronate",
    "routine.manual.quasiDrug": "医薬部外品",
    "routine.manual.back": "← スキャンに戻る",
    "routine.manual.add": "ルーティンに追加",
    "routine.manual.adding": "追加中…",

    "check.title": "製品チェック",
    "check.sub.personalised": "{name}さん向けにパーソナライズ。",
    "check.sub.anon": "匿名でスキャン中 — パーソナライズするにはユーザーを選択してください。",
    "check.takePhoto": "📷 写真を撮る",
    "check.uploadHint": "スマホのカメラを使うか、上の枠に既存の写真をドロップ／選択してください。",
    "check.scan": "製品をスキャン",
    "check.scanning": "スキャン中…",
    "check.save.prompt": "気に入りましたか？棚に追加しましょう。",
    "check.save.button": "ルーティンに保存",
    "check.save.saved": "✓ ルーティンに保存しました。",
    "check.save.selectUser": "この製品をルーティンに保存するにはユーザーを選択してください。",

    "pipeline.title": "分析中…",
    "pipeline.step1": "画像をスキャン中…",
    "pipeline.step2": "成分を抽出中…",
    "pipeline.step3": "危険な成分を確認中…",
    "pipeline.step4": "ルーティンと比較中…",
    "pipeline.step5": "{name}さんへのおすすめを作成中…",
    "pipeline.note": "最大1分ほどかかります。",
    "pipeline.you": "あなた",

    "scan.status.complete.label": "完了",
    "scan.status.complete.blurb": "詳しいおすすめを作成しました。",
    "scan.status.retake_required.label": "撮り直しが必要",
    "scan.status.retake_required.blurb": "成分表示を読み取れませんでした — 明るくはっきりした写真でお試しください。",
    "scan.status.action_needed.label": "確認が必要",
    "scan.status.action_needed.blurb": "製品の特定または成分の確認が必要です。",
    "scan.status.incomplete.label": "未完了",
    "scan.status.incomplete.blurb": "アドバイスを生成できませんでした。",
    "scan.coachTitle": "あなたのコーチから",
    "scan.recoLabel": "あなたへのおすすめ度",
    "scan.coach.timing": "使用タイミング",
    "scan.coach.timing.AM": "朝（AM）",
    "scan.coach.timing.PM": "夜（PM）",
    "scan.coach.timing.AM & PM": "朝・夜",
    "scan.coach.frequency": "使用頻度",
    "scan.coach.warnings": "注意事項",
    "scan.coach.howToApply": "使い方のポイント",
    "scan.coach.fit": "ルーティンへの取り入れ方",
    "scan.meta.source": "ソース",
    "scan.meta.ingredientsVia": "成分の取得元",
    "scan.meta.language": "言語",
    "scan.meta.confidence": "信頼度",
    "scan.safety": "安全性",
    "scan.safety.safe": "安全度 {pct}",
    "scan.safety.conflicts": "成分の競合",
    "scan.safety.flagged": "注意が必要な成分",
    "scan.safety.none": "安全性の問題はありません。👍",
    "scan.fitTitle": "ルーティンとの相性",
    "scan.fit.conflicts": "競合",
    "scan.fit.redundant": "重複の可能性",
    "scan.fit.valueAdd": "追加価値",
    "scan.ingredients": "成分（{count}）",
    "scan.unmatched": "未照合：{list}",
    "scan.sources": "出典",
  },
};

// Canonical stored value → Japanese label (skin types, goals, conditions, etc.).
// English display falls back to prettify(), so only the JA side is listed here.
export const TERMS_JA: Record<string, string> = {
  // skin type
  dry: "乾燥肌",
  oily: "脂性肌",
  combination: "混合肌",
  normal: "普通肌",
  sensitive: "敏感肌",
  // sun damage
  none: "なし",
  mild: "軽度",
  moderate: "中程度",
  severe: "重度",
  // conflict severity
  high: "高",
  medium: "中",
  low: "低",
  // goals
  "fine lines": "小じわ",
  "deep wrinkles": "深いしわ",
  "sagging skin": "たるみ",
  "hollowness/volume loss": "ボリュームの減少・こけ",
  "crepey/thin skin": "ちりめんじわ・薄い肌",
  hyperpigmentation: "色素沈着",
  melasma: "肝斑",
  redness: "赤み",
  dullness: "くすみ",
  "uneven skin": "肌の色むら",
  acne: "ニキビ",
  "blackheads/whiteheads": "黒ずみ・白ニキビ",
  "acne scars": "ニキビ跡",
  "dryness/dehydration": "乾燥・水分不足",
  "flakiness/peeling": "皮むけ・粉ふき",
  rosacea: "酒さ",
  "enlarged pores": "毛穴の開き",
  oiliness: "皮脂・テカリ",
  "blue circles": "青クマ",
  "crow's feet": "目尻のしわ",
  "under-eye bags": "目の下のたるみ",
  // skin conditions
  eczema: "湿疹",
  psoriasis: "乾癬",
};

export function localizeTerm(lang: Lang, value: string): string {
  if (lang === "ja") return TERMS_JA[value] ?? value;
  return prettify(value);
}

// --- price formatting -------------------------------------------------------

function yen(amount: number): string {
  return `¥${Math.round(amount).toLocaleString("ja-JP")}`;
}

function usd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

// A per-product monthly price label for the routine list.
export function formatProductPrice(
  lang: Lang,
  p: {
    monthly_cost_usd?: number | null;
    monthly_cost_native?: number | null;
    price_usd?: number | null;
    price_native?: number | null;
    price_currency?: string | null;
  },
): string {
  if (lang === "ja") {
    if (p.monthly_cost_native != null && p.price_currency === "JPY")
      return `≈ ${yen(p.monthly_cost_native)}/月`;
    if (p.price_native != null && p.price_currency === "JPY")
      return yen(p.price_native);
  }
  if (p.monthly_cost_usd != null) return `≈ ${usd(p.monthly_cost_usd)}/mo`;
  if (p.price_usd != null) return usd(p.price_usd);
  return "—";
}

// The routine's total monthly cost, in the active language's currency.
export function formatMonthlyTotal(
  lang: Lang,
  d: { monthly_cost_usd?: number | null; monthly_cost_jpy?: number | null },
): string | null {
  if (lang === "ja") return d.monthly_cost_jpy != null ? yen(d.monthly_cost_jpy) : null;
  return d.monthly_cost_usd != null ? `$${d.monthly_cost_usd.toFixed(2)}` : null;
}

// The USD-stored budget, shown in the active language's currency.
export function formatBudget(lang: Lang, usdAmount: number, max: number): string {
  if (lang === "ja") {
    const v = usdAmount * BUDGET_USD_TO_JPY;
    return usdAmount >= max ? `${yen(max * BUDGET_USD_TO_JPY)}+` : yen(v);
  }
  return usdAmount >= max ? `$${max}+` : `$${usdAmount}`;
}
