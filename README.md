# 🚀 事業開発部向け AIトレンド・ビジネス創出エージェント

世の中の最新IT・AIニュースを自動収集し、**「課題（Pain）× 最新技術（Tech）× マネタイズ（Biz Model）」**の視点から具体的な事業アイデアと打ち手を立案して、**Outlookメール** または **Teams**（またはローカルMarkdown）に通知するAIエージェントです。

---

## 🌟 主な特徴

1. **ユーザー・自社ごとのプロファイリング**
   - 自社ホームページのURLやテキストメモを指定するだけで、AIが自社の「強み・保有アセット・ターゲット・注力領域」を自動分析。自社に最適化された提案を創出します。
2. **多段パイプラインによる高精度なアイデア創出**
   - ニュース収集 → 自社親和性スコアリング → 課題＆技術抽出 → マネタイズモデル立案 の段階的思考を実行。
3. **完全無料運用が可能（ランニングコスト0円）**
   - Google Gemini API（Google AI Studio）の無料枠（Free Tier）を利用。
4. **Outlook（メール）& Teams（チャット/チャネル）両対応**
   - **Outlook:** 社内の特別な設定や管理者権限が不要。指定したアドレス宛てに美しいHTMLメールで届きます。
   - **Teams:** チャネルだけでなく「自分とのチャット」や「グループチャット」への通知も可能。

---

## 📁 ディレクトリ構成

```text
├── config.yaml          # ユーザー設定（自社URL、注力テーマ、通知先設定など）
├── .env.example         # APIキーやWebhook URLのテンプレート
├── main.py              # 実行エントリーポイント
├── profiler.py          # 自社URL・メモから企業プロファイルを分析・生成
├── collector.py         # Google News RSS等からのニュース収集
├── analyzer.py          # 記事選定・事業アイデア・マネタイズモデルの生成
├── notifier.py          # Outlookメール送信（HTML）/ Teams送信 / Markdown保存
├── models.py            # データモデル定義 (Pydantic)
├── requirements.txt     # 依存ライブラリ一覧
├── reports/             # 生成された週次レポート（Markdown）の保存先
└── .github/workflows/   # GitHub Actions (週1回自動実行設定)
```

---

## 🛠️ セットアップ手順

### 1. Gemini APIキーの取得（完全無料・約3分）

1. ブラウザで [Google AI Studio](https://aistudio.google.com/) を開きます。
2. Googleアカウントでログインし、左上の **「Get API key」** → **「Create API key」** を押します。
3. 表示された `AIzaSy...` から始まるキーをコピーします。

### 2. 環境変数の設定 (`.env`)

`.env.example` をコピーして `.env` を作成し、取得したキーを貼り付けます：

```ini
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxx
```

### 3. 設定ファイルのカスタマイズ ([config.yaml](file:///c:/Users/5014432/Desktop/a/config.yaml))

[config.yaml](file:///c:/Users/5014432/Desktop/a/config.yaml) を開き、通知先と自社情報を設定します。

#### 【Outlookにメールで送りたい場合（最もおすすめ）】
```yaml
notification:
  channel: "outlook"
  outlook:
    to_email: "your_name@your_company.co.jp" # あなたのメールアドレス
    display_only: false # trueにすると、送信前にメールの下書き画面がポップアップします
```

#### 【Teamsチャットに送りたい場合】
Teamsの「ワークフロー」でチャット宛てWebhookを作成し、`.env` にURLを設定した上で以下のように指定します：
```yaml
notification:
  channel: "teams"
```

---

## 🏃 実行方法

PowerShellでプロジェクトフォルダ（`C:\Users\5014432\Desktop\a`）に移動して実行します：

```powershell
# 1. テスト実行（通知を送らず、画面とファイルでレポートを確認）
.\.venv\Scripts\python.exe main.py --dry-run

# 2. 本番実行（Outlookから自分宛てにメール送信 ＆ reports/ に保存）
.\.venv\Scripts\python.exe main.py

# 3. 自社のプロファイル（URL/メモ）を再読み込み・再生成したい場合
.\.venv\Scripts\python.exe main.py --refresh-profile
```
