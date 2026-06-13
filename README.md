# 🌿 SkinGraph — AIマルチモーダル スキンケア解析パイプライン

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-1C3C3C?style=for-the-badge&logo=chainlink&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-VLM_Inference-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active_Development-brightgreen?style=for-the-badge)

**階層型VLM推論・決定論的自己修正・レジストリグラウンディングによる、信頼性工学に基づいたプロダクションレベルのスキンケアラベル解析スペシャリストシステムです。**

[日本語](#japanese) · [English](#english)

</div>

---

<a name="japanese"></a>

## 🧠 エンジニアリング設計思想

SkinGraphは、確率論的な「ブラックボックス」OCRとは異なり、**信頼性工学に基づいたスペシャリストシステム**として設計されています。3つのL6レベルの設計原則を軸に構築されています。

1. **階層型推論とコスト効率** — 「Flash優先」アーキテクチャにより、標準的なラベルの約80%を1/10のコストで処理します。Proモデルは、湾曲・グレア・低コントラストなど「逆境的な視覚条件」に対してのみ起動します。
2. **決定論的自己修正** — 盲目的なリトライではなく、専用の**修正ノード**が失敗した抽出の信頼スコアを読み取り、具体的なフィードバックを生成して次のFlashプロンプトに注入します。追加のLLM呼び出しはゼロ。最大2回の修正後、自動的にProへエスカレーション。
3. **決定論的グラウンディング** — ファジーマッチングによるレジストリエンジンが、確率論的なVLM出力を100%正確な検証済み成分リストに「ヒーリング（修復）」します。安全性に関わるデータが「推測」されることを根本的に防ぎます。

---

## 🏗️ システムアーキテクチャ

### Level 2 — 機能ブロック図

```mermaid
flowchart TB
    User(["📱 ユーザー\n（モバイルアプリ）"])
    Ingest["🖼️ 画像前処理\n適応型ダウンスケーリング\nJPEG 85% / 2048px"]
    VLM["🤖 階層型推論エンジン\nGemini Flash → Pro"]
    Registry["📚 レジストリエンジン\nファジーグラウンディング · rapidfuzz"]
    Coach["💬 スペシャリストロジック\n安全性監査 & 成分正規化"]
    Retake["🔁 グレースフルイグジット\nユーザーUXフィードバック"]

    User -->|"高解像度画像"| Ingest
    Ingest -->|"最適化ペイロード"| VLM
    VLM -->|"高信頼スコア"| Registry
    VLM -->|"回復不能"| Retake
    Registry -->|"INCI標準データ"| Coach
    Coach -->|"安全性レポート"| User
    Retake -->|"再撮影プロンプト"| User
```

### Level 3 — LangGraphオーケストレーション

```mermaid
flowchart TD
    Start(["🚀 開始"])
    Flash["⚡ Flashスキャナー\nGemini Flash\n構造化出力"]
    Router{"🔀 推論ルーター\n信頼スコア閾値"}
    EarlyCheck["🔍 早期レジストリヒット\n99%マッチ閾値\nループショートサーキット"]
    Correction["📝 修正フィードバックノード\n決定論的フィードバック生成\n次のプロンプトに注入"]
    Pro["🧠 Proスキャナー\nGemini Pro\n空間推論フォーカス"]
    RegLookup["📚 最終レジストリマッチ\n90%マッチ閾値\nデータヒーリング"]
    ProRouter{"🔀 Pro品質ゲート"}
    Retake["🔁 再撮影ハンドラー\nUX例外ロジック"]
    End1(["✅ 終了"])
    End2(["✅ 終了"])
    End3(["❌ 終了（UXアラート）"])

    Start --> Flash
    Flash --> Router

    Router -->|"conf ≥ 0.85 ✅"| RegLookup
    Router -->|"0.50 ≤ conf < 0.85 ⚠️"| EarlyCheck
    Router -->|"conf < 0.50 🚨"| Pro

    EarlyCheck -->|"≥ 99% 一致 🎯\nLLMリトライをスキップ"| End1
    EarlyCheck -->|"< 99% ミス"| Correction
    Correction -->|"批評注入\n反復回数 +1"| Flash

    RegLookup --> End2

    Pro --> ProRouter
    ProRouter -->|"成功"| RegLookup
    ProRouter -->|"失敗"| Retake
    Retake --> End3

    style EarlyCheck fill:#fff3cd,stroke:#ffc107
    style Correction fill:#d1ecf1,stroke:#0dcaf0
    style Retake fill:#f8d7da,stroke:#dc3545
    style Flash fill:#d4edda,stroke:#28a745
    style Pro fill:#cce5ff,stroke:#0d6efd
```

> 💡 **自己修正パターン**: `修正ノード`は決定論的なプロセスです。失敗した抽出の信頼スコアとシステムステータスを読み取り、具体的なフィードバック文字列を生成し、次のFlashプロンプトに注入します。追加のLLM呼び出しは発生しません。

---

## 🔬 評価・ベンチマーク

精度は、グレア・円筒歪み・高密度漢字を含む **ゴールデンセット画像** で `evaluate.py` を使用し計測しています。

| 指標 | Flash (`gemini-3.1-flash-lite`) | Pro (`gemini-3.1-pro-preview`) |
|---|---|---|
| 成分抽出 F1（平均） | **0.97** | **0.98** |
| 成分再現率（平均） | 0.98 | 0.99 |
| ブランド / 製品名一致 | 100/100 | 100/100 |
| 医薬部外品検出 | 2/2 ✓ | 2/2 ✓ |
| 平均 API レイテンシ | ~6–7s | ~30–35s |

`evaluate.py` を使用し、手動アノテーション済み成分リストとのフィールドレベルF1で評価。

> ⚠️ N=2（prod_001: 難易度8、prod_002: 難易度7）。いずれも逆境的条件（円筒歪み・鏡面反射・高密度漢字）を含む。グラウンドトゥルースの拡充に伴い、ベンチマークを更新予定。

---

## 🛠️ パフォーマンスとスケーラビリティの設計判断

**なぜLangGraph？** 単純なリニアチェーンは自己修正に対応できません。LangGraphのサイクリック状態管理により、システムが自身の抽出失敗の「短期記憶」を保持し、修正ループを実現します。

**RapidFuzz WRatio**: OCRによる文字欠落や日本語文字の揺れに対して堅牢なため、アイデンティティマッチングに採用。

**Vector DB ロードマップ**: 現在はPoC用ローカルJSONを使用。100万SKUへのスケールに向けてpgvectorまたはPineconeへの移行を設計済み。

---

## ✨ 主な機能

| 機能 | 詳細 |
|---|---|
| ⚡ **階層型VLM推論** | Flash優先、信頼スコアに基づいてProへ自動エスカレーション |
| 🔄 **自己修正ループ** | 最大2回のフィードバック付き再試行 |
| 🔍 **早期レジストリ照合** | 初回スキャン後に99%ファジーマッチ → 修正LLMコールをスキップ |
| 📚 **検証済みレジストリマッチング** | rapidfuzz WRatioスコアリングによるキュレーション済みデータベース照合 |
| 🗾 **日本語ラベル特化** | JCIA基準成分正規化、医薬部外品検出 |
| 🖼️ **画像最適化** | 推論前に最大2048pxへ自動ダウンスケール（ペイロード60〜80%削減） |
| 🔭 **評価ハーネス** | `evaluate.py` — 成分F1・バイリンガルブランド照合・NFKC正規化による精度計測 |
| 🧩 **構造化出力契約** | Pydantic v2による`ProductExtraction`スキーマ強制 |

---

## 🚀 セットアップ

```bash
git clone <your-repo-url>
cd skincare-coach
poetry install
```

> **OCRについて:** `scripts/run_ocr.py` はオープンソースの日本語OCRエンジン（YomiToku）をゴールデンセット画像に対して実行し、プレーンテキストを `data/ocr_out/` に出力します。これは **Phase 0ベンチマーク** として、OCRとVLMの精度差を定量化するためだけに存在します。プロダクショングラフ（`src/graph.py`）には組み込まれておらず、グラフはGemini VLM推論のみを使用します。

`.env`ファイルを作成:

```env
GOOGLE_API_KEY=your_key_here
```

実行:

```bash
# 単一画像（裏ラベル・デフォルト）
poetry run python run_pipeline.py data/golden_set/prod_001.jpg

# 表ラベル
poetry run python run_pipeline.py data/golden_set/prod_001.jpg --image-type front

# Flash vs Pro 比較テスト
poetry run python test_scanner.py
```

---

## 🗺️ ロードマップ

- [ ] 🌐 **セマンティック多言語対応** — 日本語・韓国語・英語の名称を単一のUniversal INCI IDにマッピング
- [ ] 🔬 **安全性監査エンジン** — 成分禁忌（レチノール/AHA）のハードコード型トゥルーステーブル
- [ ] 📱 **API抽象化** — 本番デプロイ向けFastAPIラッパー
- [ ] 🏷️ **バーコード統合** — JAN/UPCコード事前照合で既知商品のVLMを完全スキップ
- [ ] 💬 **コーチノード** — パーソナライズされたスキンケアルーティンアドバイス

---

<div align="center">

Built with ❤️ and matcha 🍵

</div>

---
---

<a name="english"></a>

# 🌿 SkinGraph — AI Multimodal Skincare Analysis Pipeline

<div align="center">

**A production-grade Specialist System for skincare label extraction, built on Reliability Engineering principles: Tiered VLM Inference, Deterministic Self-Correction, and Fuzzy Registry Grounding.**

</div>

---

## 🧠 Engineering Philosophy

Most OCR implementations are stochastic "black boxes." SkinGraph is architected as a **Specialist System** built around three L6-level reliability engineering principles:

1. **Tiered Inference & Cost Efficiency** — A "Flash-First" strategy handles ~80% of standard labels at 1/10th the cost of Pro. Pro models are reserved for adversarial visual conditions: cylindrical distortion, specular glare, and low-contrast multilingual text.
2. **Deterministic Self-Correction** — Instead of blind retries, a dedicated **Correction Node** reads the failed extraction's confidence score and status, generates a targeted feedback string, and injects it into the next Flash prompt — at zero additional LLM cost. Up to 2 iterations before automatic Pro escalation.
3. **Deterministic Grounding** — A fuzzy-matching Registry Engine "heals" probabilistic VLM outputs by snapping them to 100% accurate, verified ingredient lists. Safety-critical data is never left to probabilistic inference.

---

## 🏗️ System Architecture

### Level 2 — Functional Block Diagram

```mermaid
flowchart TB
    User(["📱 User\n(Mobile App)"])
    Ingest["🖼️ Image Pre-processing\nAdaptive Downscaling\nJPEG 85% / 2048px"]
    VLM["🤖 Tiered Inference Engine\nGemini Flash → Pro"]
    Registry["📚 Registry Engine\nFuzzy Grounding · rapidfuzz"]
    Coach["💬 Specialist Logic\nSafety Audit & Normalization"]
    Retake["🔁 Graceful Exit\nUser UX Feedback"]

    User -->|"High-res image"| Ingest
    Ingest -->|"Optimized Payload"| VLM
    VLM -->|"High Confidence"| Registry
    VLM -->|"Unrecoverable"| Retake
    Registry -->|"INCI Standard Data"| Coach
    Coach -->|"Safety Report"| User
    Retake -->|"Retake Prompt"| User
```

### Level 3 — LangGraph Orchestration

```mermaid
flowchart TD
    Start(["🚀 START"])
    Flash["⚡ Flash Scanner\nGemini Flash\nStructured Output"]
    Router{"🔀 Inference Router\nConfidence Thresholds"}
    EarlyCheck["🔍 Early Registry Hit\n99% Match Threshold\nShort-circuit loop"]
    Correction["📝 Correction Node\nDeterministic Feedback\nInjected into next prompt"]
    Pro["🧠 Pro Scanner\nGemini Pro\nSpatial Reasoning Focus"]
    RegLookup["📚 Final Registry Match\n90% Match Threshold\nData Healing"]
    ProRouter{"🔀 Pro Quality Gate"}
    Retake["🔁 Retake Handler\nUX Exception Logic"]
    End1(["✅ END"])
    End2(["✅ END"])
    End3(["❌ EXIT (UX Alert)"])

    Start --> Flash
    Flash --> Router

    Router -->|"conf ≥ 0.85 ✅"| RegLookup
    Router -->|"0.50 ≤ conf < 0.85 ⚠️"| EarlyCheck
    Router -->|"conf < 0.50 🚨"| Pro

    EarlyCheck -->|"≥ 99% Match 🎯\nSkip LLM Retry"| End1
    EarlyCheck -->|"< 99% Miss"| Correction
    Correction -->|"Injected Critique\nIteration +1"| Flash

    RegLookup --> End2

    Pro --> ProRouter
    ProRouter -->|"Success"| RegLookup
    ProRouter -->|"Fail"| Retake
    Retake --> End3

    style EarlyCheck fill:#fff3cd,stroke:#ffc107
    style Correction fill:#d1ecf1,stroke:#0dcaf0
    style Retake fill:#f8d7da,stroke:#dc3545
    style Flash fill:#d4edda,stroke:#28a745
    style Pro fill:#cce5ff,stroke:#0d6efd
```

> 💡 **Self-Correction Pattern**: The `Correction Node` is deterministic — no additional LLM call is made. It reads the failed extraction's confidence score and system status, generates a targeted feedback string, and injects it into the next Flash prompt. Up to 2 iterations before escalating to Pro.

---

## ✨ Key Features

| Feature | Detail |
|---|---|
| ⚡ **Tiered VLM Inference** | Flash-first with automatic Pro escalation based on confidence score |
| 🔄 **Self-Correction Loop** | Up to 2 feedback-enriched retries before escalation |
| 🔍 **Early Registry Short-Circuit** | 99% fuzzy match after first scan skips the correction LLM call |
| 📚 **Verified Registry Matching** | rapidfuzz WRatio scoring against a curated product database |
| 🗾 **Japanese Label Specialisation** | JCIA-standard ingredient normalisation, quasi-drug (`医薬部外品`) detection |
| 🖼️ **Image Optimisation** | Auto-downscale to 2048px max before inference — cuts payload 60–80% |
| 🔭 **Eval Harness** | `evaluate.py` — field-level ingredient F1, bilingual brand/product match, NFKC normalization |
| 🧩 **Structured Output Contract** | Pydantic-enforced `ProductExtraction` schema — no prompt-parsing fragility |

---

## 🛠️ Tech Stack

```
Orchestration     LangGraph (StateGraph + conditional routing)
VLM Inference     Google Gemini Flash / Pro via langchain-google-genai
Fuzzy Matching    rapidfuzz (WRatio scorer)
String Matching   pyahocorasick (multi-pattern exact match)
Data Contracts    Pydantic v2
Image Processing  Pillow (LANCZOS downscale → JPEG 85) · OpenCV (CLAHE + cylindrical dewarping)
Config            python-dotenv
Package Manager   Poetry
```

---

## 📁 Project Structure

```
skincare-coach/
├── src/
│   ├── graph.py          # LangGraph workflow definition & routers
│   ├── state.py          # AgentState TypedDict + Pydantic data contracts
│   ├── config.py         # Centralised thresholds & model IDs
│   └── nodes/
│       ├── scanner.py    # Flash & Pro VLM nodes + image optimisation
│       ├── registry.py   # Fuzzy registry match (early check + full lookup)
│       ├── auditor.py    # Safety audit node (in progress)
│       └── coach.py      # Advice generation node (in progress)
├── data/
│   ├── golden_set/          # 40 product label images (2 ground-truthed)
│   ├── ground_truth.json    # Annotated ground truth (brand, ingredients, safety triggers)
│   ├── registry.json        # Verified product + ingredient database
│   ├── ingredients.json     # JCIA ingredient reference
│   └── ocr_out/             # Raw OCR text output (benchmark artefacts, not production)
├── scripts/
│   └── run_ocr.py           # ⚠️ Standalone OCR benchmark — NOT wired into the graph
├── run_pipeline.py          # CLI entry point
├── evaluate.py              # Extraction accuracy scorer (VLM output vs ground truth)
└── test_scanner.py          # Flash vs Pro head-to-head test harness
```

> **Note on OCR:** `scripts/run_ocr.py` runs a local YomiToku Japanese OCR engine on the golden-set images and writes plain-text output to `data/ocr_out/`. It exists purely as a **Phase 0 benchmark baseline** to quantify the OCR-vs-VLM accuracy gap — it is intentionally excluded from the production graph (`src/graph.py`). The graph uses Gemini VLM inference exclusively.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/)
- Google AI API key (Gemini access)

### Installation

```bash
git clone <your-repo-url>
cd skincare-coach
poetry install
```

### Environment Setup

Create a `.env` file:

```env
GOOGLE_API_KEY=your_key_here
```

### Run

```bash
# Single image — back label (default)
poetry run python run_pipeline.py data/golden_set/prod_001.jpg

# Front label
poetry run python run_pipeline.py data/golden_set/prod_001.jpg --image-type front

# Flash vs Pro comparison
poetry run python test_scanner.py
```

---

## 🔬 Evaluation & Benchmarking

Accuracy is measured with `evaluate.py` against a hand-annotated ground truth, using field-level F1 scoring with NFKC normalization and bilingual fuzzy matching.

| Metric | Flash (`gemini-3.1-flash-lite`) | Pro (`gemini-3.1-pro-preview`) |
|---|---|---|
| Ingredient F1 (avg) | **0.97** | **0.98** |
| Ingredient Recall (avg) | 0.98 | 0.99 |
| Brand / Product Match | 100/100 | 100/100 |
| Quasi-drug Detection | 2/2 ✓ | 2/2 ✓ |
| Avg. API Latency | ~6–7s | ~30–35s |

> ⚠️ N=2 (prod_001: difficulty 8, prod_002: difficulty 7). Both include adversarial conditions: cylindrical distortion, specular reflection, dense kanji clusters. Benchmark expands as ground truth grows.

---

## 🛠️ Performance & Scalability Decisions

**Why LangGraph?** Simple linear chains cannot implement self-correction. LangGraph's cyclic state management allows the system to maintain short-term memory of its own extraction failures across iterations.

**RapidFuzz WRatio**: Chosen for identity matching due to its resilience against OCR-induced character deletions and Japanese character variations (e.g., full-width vs. half-width, katakana normalization).

**Vector DB Roadmap**: Currently using local JSON for PoC. Architected to migrate to pgvector or Pinecone for 10⁶ SKU scalability without code changes to the registry interface.

---

## 🗺️ Roadmap

- [ ] 🌐 **Semantic Multilingual Support** — Map Japanese, Korean, and English names to a single Universal INCI ID
- [ ] 🔬 **Safety Audit Engine** — Hard-coded Truth Table for ingredient contraindications (Retinol/AHA, Niacinamide/Vitamin C)
- [ ] 📱 **API Abstraction** — FastAPI wrapper for production deployment
- [ ] 🏷️ **Barcode Integration** — Pre-scan JAN/UPC codes to skip VLM entirely for known products
- [ ] 💬 **Coach Node** — Personalised skincare routine advice engine
