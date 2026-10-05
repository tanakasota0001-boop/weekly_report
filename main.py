import os
import sys
import argparse
import logging
import yaml
from dotenv import load_dotenv

# WindowsコンソールでのUnicodeEncodeError (絵文字など) を防止
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from profiler import build_company_profile
from collector import collect_news
from analyzer import generate_growth_analysis
import profile_manager
from notifier import (
    save_markdown_report,
    send_to_teams,
    send_via_outlook,
    send_via_gmail,
    format_report_to_markdown
)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BusinessGrowthAgent")


def load_configuration(config_path: str = "config.yaml"):
    """config.yaml と .env を読み込む"""
    load_dotenv()

    if not os.path.exists(config_path):
        logger.error(f"設定ファイルが見つかりません: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def main():
    parser = argparse.ArgumentParser(description="ビジネス成長AIエージェント (Business Growth Agent)")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルのパス")
    parser.add_argument("--profile", default=None, help="対象プロファイルID (例: haveasite, local_cafe, ai_saas_creator)")
    parser.add_argument("--dry-run", action="store_true", help="通知送信を行わず、ローカル出力のみ実行する")
    parser.add_argument("--refresh-profile", action="store_true", help="自社プロファイルを再生成する")
    parser.add_argument("--ui", "--web", action="store_true", dest="run_web", help="Webダッシュボード（GUI）をブラウザで起動する")
    parser.add_argument("--port", type=int, default=8000, help="Webダッシュボードの待受ポート (デフォルト: 8000)")
    args = parser.parse_args()

    if args.run_web:
        from web_app import start_server
        start_server(port=args.port, open_browser=True)
        return

    logger.info("==========================================")
    logger.info("  ビジネス成長AIエージェント 起動")
    logger.info("==========================================")

    # 1. 設定読み込み
    config = load_configuration(args.config)
    api_key = os.getenv("GEMINI_API_KEY")
    teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "")

    if not api_key or api_key == "your_gemini_api_key_here":
        logger.error("【エラー】GEMINI_API_KEY が設定されていません。")
        print("\n" + "=" * 60)
        print("【セットアップ手順】")
        print("1. Google AI Studio ( https://aistudio.google.com/ ) からAPIキーを無料取得してください。")
        print("2. プロジェクト直下の `.env` ファイルに `GEMINI_API_KEY=取得したキー` を記載してください。")
        print("=" * 60 + "\n")
        sys.exit(1)

    model_name = config.get("model", {}).get("name", "gemini-2.5-flash")
    comp_cfg = config.get("company", {})
    news_cfg = config.get("news", {})
    research_cfg = config.get("research", {})
    notif_cfg = config.get("notification", {})

    # プロファイルの選択と解決
    profile_id = args.profile or profile_manager.get_active_profile_id()
    active_profile_data = profile_manager.get_profile(profile_id)
    if active_profile_data:
        logger.info(f"プロファイル '{profile_id}' ({active_profile_data.get('name')}) をロードしました。")
        comp_cfg = {
            "name": active_profile_data.get("name", comp_cfg.get("name")),
            "url": active_profile_data.get("url", comp_cfg.get("url")),
            "notes": active_profile_data.get("notes", comp_cfg.get("notes")),
            "current_challenges": active_profile_data.get("current_challenges", comp_cfg.get("current_challenges")),
            "resource_constraints": active_profile_data.get("resource_constraints", comp_cfg.get("resource_constraints")),
        }
        # プロファイル固有のキーワードがあれば優先
        if active_profile_data.get("keywords"):
            news_cfg["keywords"] = active_profile_data["keywords"]
    else:
        logger.warning(f"指定されたプロファイル '{profile_id}' が見つからないため、config.yaml の設定を使用します。")
        profile_id = None

    # 2. 自社プロファイルの構築
    logger.info("\n--- [Step 1/4] 自社プロファイルの準備 ---")
    profile = build_company_profile(
        api_key=api_key,
        model_name=model_name,
        name=comp_cfg.get("name", "自社"),
        url=comp_cfg.get("url", ""),
        notes=comp_cfg.get("notes", ""),
        force_refresh=args.refresh_profile,
        current_challenges=comp_cfg.get("current_challenges"),
        resource_constraints=comp_cfg.get("resource_constraints"),
        profile_id=profile_id
    )
    print(f"\n[対象プロファイル]: {profile.name} (ID: {profile_id or 'default'})")
    print(f"・主要事業: {profile.core_business}")
    print(f"・ターゲット: {profile.target_customers}")
    print(f"・保有アセット: {', '.join(profile.key_assets)}")
    print(f"・注力テーマ: {', '.join(profile.focus_themes)}")
    if profile.current_challenges and profile.current_challenges.get("focus_kpi"):
        print(f"・🎯 重点KPI: {profile.current_challenges.get('focus_kpi')}")
    if profile.resource_constraints:
        rc = profile.resource_constraints
        print(f"・🛠️ リソース制約: 工数:{rc.get('weekly_hours', '未設定')} / 予算:{rc.get('budget', '未設定')} / スキル:{rc.get('technical_skill', '未設定')} / 体制:{rc.get('team_size', '未設定')}")
    print()

    # 3. ニュース収集 & 課題逆引きリサーチ
    logger.info("--- [Step 2/4] 課題逆引きリサーチ & 国内・海外ニュース収集 ---")
    keywords = news_cfg.get("keywords", ["生成AI ビジネス", "DX 新規事業"])
    max_collect = news_cfg.get("max_articles_to_collect", 25)
    global_cfg = news_cfg.get("global_sources", {})
    articles = collect_news(
        keywords=keywords,
        max_total_articles=max_collect,
        global_config=global_cfg,
        profile=profile,
        api_key=api_key,
        model_name=model_name
    )

    if not articles:
        logger.warning("収集できたニュース記事がありませんでした。キーワードを見直してください。")
        sys.exit(0)

    # 4. 分析 & ビジネス創出アイデア生成
    logger.info("\n--- [Step 3/4] ビジネス成長分析 & アイデア生成 ---")
    top_n = news_cfg.get("top_articles_to_report", 3)
    report = generate_growth_analysis(
        api_key=api_key,
        model_name=model_name,
        articles=articles,
        profile=profile,
        top_n=top_n,
        research_config=research_cfg
    )

    # 5. レポート保存 & 通知
    logger.info("\n--- [Step 4/4] レポート保存 & 通知 ---")
    if notif_cfg.get("save_markdown_locally", True):
        saved_file = save_markdown_report(report)
        print(f"\n[保存完了] レポートが保存されました: {saved_file}")

    # コンソールにレポートのプレビューを表示
    print("\n" + "=" * 60)
    print(format_report_to_markdown(report))
    print("=" * 60 + "\n")

    if args.dry_run:
        logger.info("Dry-run モードのため、通知送信をスキップしました。")
        logger.info("全ステップが完了しました。")
        return

    # 送信チャンネルの判定
    channel = notif_cfg.get("channel", "gmail").lower()

    if channel == "gmail":
        gmail_user = os.getenv("GMAIL_USER", "")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        gmail_cfg = notif_cfg.get("gmail", {})
        to_email = gmail_cfg.get("to_email", "") or gmail_user
        if not gmail_user or not gmail_password:
            logger.warning(
                "【Gmail未設定】 .env に GMAIL_USER と GMAIL_APP_PASSWORD を設定してください。"
                "設定されるまでメール送信はスキップされ、ローカルのMarkdownファイルのみ保存されます。"
            )
        else:
            send_via_gmail(report, gmail_user=gmail_user, gmail_password=gmail_password, to_email=to_email)

    elif channel == "outlook":
        outlook_cfg = notif_cfg.get("outlook", {})
        to_email = outlook_cfg.get("to_email", "")
        display_only = outlook_cfg.get("display_only", False)
        if to_email and "example.com" not in to_email:
            send_via_outlook(report, to_email=to_email, display_only=display_only)
        else:
            logger.warning("config.yaml の notification.outlook.to_email に正しいメールアドレスを設定してください。")

    elif channel == "teams":
        if teams_webhook and teams_webhook != "your_teams_webhook_url_here":
            send_to_teams(teams_webhook, report)
        else:
            logger.warning("TEAMS_WEBHOOK_URL が設定されていないため、Teams送信はスキップされました。")
    elif channel == "none":
        logger.info("通知チャンネルは 'none' のため、メール/Teams送信は行いません（レポートはローカルに保存済みです）。")
    else:
        logger.info(f"通知チャンネルは '{channel}' に設定されています（通知はスキップされました）。")

    logger.info("全ステップが完了しました。")


if __name__ == "__main__":
    main()
