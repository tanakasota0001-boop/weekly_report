# 🚀 ビジネス成長AIエージェント (Strategic Growth Studio)

世の中の最新IT・AIニュースおよび**海外先行SaaS・プロダクト動向**を自動収集し、**「ペイン（課題）× 最新技術 × マネタイズ・ビジネス成長」**の視点から具体的な事業アイデアと打ち手を立案。さらに**「攻め（事業案）」**だけでなく**「守り・リスク（客観的批判・失敗要因）」**まで多角的に分析し、**直感的なWebダッシュボード**、**Gmail**、**Outlook**、**Teams**、ローカルMarkdownに届ける戦略参謀AIエージェントです。

---

## 🌟 主な特徴 & UI/UX

1. **💻 洗練された戦略Webダッシュボード (Web UI)**
   - ブラウザ上で過去レポートの閲覧、アイデアのフィルタリング（国内/海外/高実現性）、Markdownダウンロード、ワンクリックGmail送信が可能。
   - レポート生成スタジオでは、4ステップの進捗ステッパーとリアルタイムログコンソールで進行状況をリアルタイム監視。
   - 設定マネージャーにより、自社プロファイル、重点KPI、ニュースキーワードをノーコードで直感的に変更・保存できます。

2. **自社プロファイル & 直近の重点KPIの動的反映**
   - 自社HPのURLや事業メモを指定するだけで、AIが「強み・保有アセット・ターゲット・提供価値」を自動分析（キャッシュ機能付き）。
   - 「直近の注力課題・重点KPI（例: Churn率低減、クロスセル率向上等）」を設定することで、プロファイル再生成なしで動的にアイデアの照準をチューニング。

3. **多段パイプライン & 本文スクレイピング・Web検索グラウンディング**
   - ニュース収集 → 候補スクリーニング → **元記事本文の全文スクレイピング** → **GeminiのGoogle Search Grounding（追加Web検索）** を実行。
   - 単なる要約にとどまらず、背後にある市場規模や競合他社の事例まで掘り下げた高品質なインサイトを抽出します。

4. **「攻め」と「守り（リスク・客観的批判）」の両輪評価**
   - 事業創出のポジティブな打ち手だけでなく、**「参入障壁・コモディティ化リスク」「技術的・運用の落とし穴」「コスト対効果」「客観的な批判的見解」**を明確に提示。

5. **海外トレンド・先行SaaS（Product Hunt / 米国Tech動向）のキャッチアップ**
   - 国内ニュースに加え、Product Huntや米国の最新SMB向けSaaS動向を自動収集。
   - 「日本市場や自社の顧客基盤（例: 個人店・中小企業）にどうタイムマシン的にローカライズ・展開できるか」の具体的ヒントが得られます。

6. **マルチプラットフォーム通知（Mac / Windows / Linux対応）**
   - **Web UI:** 直感的なダッシュボード上でいつでもレポート閲覧・管理。
   - **Gmail (推奨):** macOS、Linux、Windows、GitHub Actions問わず動作。HTMLメールで届きます。
   - **Outlook:** Windowsデスクトップ版Outlookから自動送信・下書き作成。
   - **Teams:** Webhook経由でチャネルやチャットに通知。

---

## 📁 ディレクトリ構成

```text
├── config.yaml          # 自社URL、重点KPI、キーワード、海外ソース、通知設定
├── .env.example         # Gemini APIキー、Gmail認証情報などのテンプレート
├── web_app.py           # Webダッシュボードサーバー (軽量・追加依存不要)
├── static/              # Webダッシュボードのフロントエンド (SPA HTML/CSS/JS)
│   └── index.html
├── main.py              # CLI & Web実行エントリーポイント
├── profiler.py          # 自社URL・メモから企業プロファイルを分析・生成
├── collector.py         # 国内Google News RSS & 海外Product Hunt/USニュース収集
├── scraper.py           # 選定記事の本文スクレイピングユーティリティ
├── analyzer.py          # 本文解析・Web検索グラウンディング・攻めと守りの戦略レポート生成
├── notifier.py          # レポート保存 / Gmail (HTML) / Outlook / Teams 通知
├── models.py            # データモデル定義 (Pydantic)
├── requirements.txt     # 依存ライブラリ一覧
└── reports/             # 生成された週次レポート (Markdown & JSON) の保存先
```

---

## 🛠️ セットアップ手順

### 1. Gemini APIキーの取得（完全無料）

1. ブラウザで [Google AI Studio](https://aistudio.google.com/) を開きます。
2. Googleアカウントでログインし、**「Get API key」** → **「Create API key」** を押します。
3. 表示されたキー（`AIzaSy...`）をコピーします。

### 2. 環境変数の設定 (`.env`)

プロジェクト直下に `.env` を作成します（`.env.example` をコピー）：

```ini
# Gemini API Key (必須)
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxx

# Gmail通知を利用する場合（Mac / Windows / Linux対応・推奨）
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Teams通知を利用する場合（任意）
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx
```

---

## 🏃 実行方法

### 1. 🌟 Webダッシュボードの起動（推奨・最も使いやすい）

以下のコマンドを実行すると、ローカルサーバーが起動しブラウザでダッシュボードが自動で開きます：

```bash
# Webダッシュボードを起動
python3 web_app.py

# または main.py 経由で起動
python3 main.py --ui
```

ブラウザで `http://localhost:8000` を開くと：
- 📊 **ダッシュボード**: 生成された最新レポートやアイデアをカード形式で閲覧・検索
- ⚡ **生成スタジオ**: ワンクリックでレポート生成を開始、リアルタイム進捗とログを確認
- 📁 **レポート履歴**: 過去のレポートを一覧表示、閲覧、Markdown保存、Gmail再送信
- 🎯 **戦略・設定**: 自社URL、重点KPI、課題リスト、キーワード、通知設定を画面から直接編集・保存

---

### 2. ターミナル（CLI）からのバッチ実行

定期実行（cronやタスクスケジューラ）やCLIから直接動かしたい場合：

```bash
# テスト実行（通知送信を行わず、コンソール表示とローカル保存のみ）
python3 main.py --dry-run

# 本番実行（レポート生成 ＆ 設定チャンネルへ送信 ＆ reports/ に保存）
python3 main.py

# 自社プロファイル（URL/メモ）を強制的に再解析・再生成する場合
python3 main.py --refresh-profile
```
