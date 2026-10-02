# 🚀 事業開発部向け AIトレンド・ビジネス創出エージェント

世の中の最新IT・AIニュースを自動収集し、**「課題（Pain）× 最新技術（Tech）× マネタイズ（Biz Model）」**の視点から具体的な事業アイデアと打ち手を立案して、週1回 **Microsoft Teams**（またはローカルMarkdown）に通知するAIエージェントです。

---

## 🌟 主な特徴

1. **ユーザー・自社ごとのプロファイリング**
   - 自社ホームページのURLやテキストメモを指定するだけで、AIが自社の「強み・保有アセット・ターゲット・注力領域」を自動分析。自社に最適化された提案を創出します。
2. **多段パイプラインによる高精度なアイデア創出**
   - ニュース収集 → 自社親和性スコアリング → 課題＆技術抽出 → マネタイズモデル立案 の段階的思考を実行。
3. **完全無料運用が可能（ランニングコスト0円）**
   - Google Gemini API（Google AI Studio）の無料枠（Free Tier）を利用。
4. **Teams 連携 & クラウド自動実行対応**
   - Teamsへのリッチカード（Adaptive Card）通知。
   - GitHub Actions を使えば、PCを閉じても毎週月曜朝に完全サーバーレスで自動配信。

---

## 📁 ディレクトリ構成

```text
├── config.yaml          # ユーザー設定（自社URL、注力テーマ、キーワード等）
├── .env.example         # APIキーやWebhook URLのテンプレート
├── main.py              # 実行エントリーポイント
├── profiler.py          # 自社URL・メモから企業プロファイルを分析・生成
├── collector.py         # Google News RSS等からのニュース収集
├── analyzer.py          # 記事選定・事業アイデア・マネタイズモデルの生成
├── notifier.py          # Teams送信（Adaptive Card）およびMarkdown保存
├── models.py            # データモデル定義 (Pydantic)
├── requirements.txt     # 依存ライブラリ一覧
├── reports/             # 生成された週次レポート（Markdown）の保存先
└── .github/workflows/   # GitHub Actions (週1回自動実行設定)
```

---

## 🛠️ セットアップ手順

### 1. 準備（APIキーとWebhookの取得）

1. **Gemini APIキーの取得（無料）:**
   - [Google AI Studio](https://aistudio.google.com/) にアクセスし、「Get API key」からAPIキーを発行します。
2. **Microsoft Teams Webhook URL の取得:**
   - レポートを投稿したいTeamsチャネルの右上「…」→「ワークフロー」または「コネクタ」を開きます。
   - 「Webhook を受信したときにチャネルに投稿する」を追加し、生成されたWebhook URLをコピーします。

### 2. 環境変数の設定

`.env.example` をコピーして `.env` ファイルを作成し、取得したキーを貼り付けます。

```bash
# Windows PowerShellの場合
Copy-Item .env.example .env
```

`.env` の内容:
```ini
GEMINI_API_KEY=AIzaSy...（取得したGeminiキー）
TEAMS_WEBHOOK_URL=https://...（取得したTeams Webhook URL）
```

### 3. 設定ファイルのカスタマイズ (`config.yaml`)

`config.yaml` を開き、自社・事業部の情報や収集キーワードを設定します。

```yaml
company:
  name: "〇〇株式会社 事業開発部"
  url: "https://your-company.co.jp" # 自社のホームページURL
  notes: |
    BtoB向けのDXや生成AIソリューションに関心が高い。
    既存の全国営業網と顧客基盤を活かした新規SaaSや伴走支援サービスを検討中。

news:
  keywords:
    - "生成AI ビジネス"
    - "DX 新規事業"
    - "AI スタートアップ 課題"
  top_articles_to_report: 3
```

---

## 🏃 実行方法

### ローカルでの手動実行

```powershell
# 仮想環境の有効化（未実施の場合）
.\.venv\Scripts\Activate.ps1

# 通常実行（分析してTeamsへ送信 ＆ reports/ に保存）
python main.py

# テスト実行（Teams送信を行わず、ローカル出力のみ確認）
python main.py --dry-run

# 自社プロファイルを再分析・再生成したい場合
python main.py --refresh-profile
```

---

## ⏰ 週1回の完全自動実行（GitHub Actions）

GitHubリポジトリにPushし、Secretsを設定するだけで毎週月曜の朝9:00（JST）に自動実行されます。

1. GitHubリポジトリの **Settings -> Secrets and variables -> Actions** を開く。
2. 以下の2つの `Repository secrets` を登録：
   - `GEMINI_API_KEY`: Google AI Studioで取得したAPIキー
   - `TEAMS_WEBHOOK_URL`: TeamsのWebhook URL
3. これで毎週月曜日に自動でTeamsにレポートが届きます。
