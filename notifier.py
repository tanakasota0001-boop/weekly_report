import os
import json
import logging
import requests
from datetime import datetime
from models import WeeklyReport

logger = logging.getLogger(__name__)

REPORTS_DIR = "reports"


def format_report_to_markdown(report: WeeklyReport) -> str:
    """レポートを読みやすいMarkdown形式にフォーマットする"""
    md = f"# {report.report_title}\n\n"
    md += f"**対象部門/企業:** {report.company_name} | **生成日:** {report.generated_at}\n\n"
    
    md += "## 💡 今週のマクロトレンド & 総括\n"
    md += f"{report.overall_trend_comment}\n\n"
    md += "---\n\n"

    for idx, idea in enumerate(report.ideas, 1):
        md += f"## 🚀 アイデア {idx}: {idea.article_title}\n"
        md += f"- **元記事リンク:** [{idea.article_title}]({idea.article_url})\n"
        md += f"- **記事の要約:** {idea.source_summary}\n\n"
        
        md += "### 1. 世の中の課題（Pain）\n"
        md += f"{idea.market_pain}\n\n"

        md += "### 2. 活用されている技術・手法（Tech）\n"
        md += f"{idea.latest_tech}\n\n"

        md += "### 3. あなたならどう解決・事業化するか（Solution & Idea）\n"
        md += f"{idea.solution_idea}\n\n"

        md += "### 4. マネタイズ・ビジネスモデル（How to Monetize）\n"
        md += f"{idea.monetization_model}\n\n"

        md += "### 5. 自社における検証論点・打ち手（Next Action）\n"
        md += f"{idea.internal_next_action}\n\n"

        md += "---\n\n"

    return md


def save_markdown_report(report: WeeklyReport) -> str:
    """レポートをローカルファイルに保存する"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"bizdev_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    content = format_report_to_markdown(report)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"レポートを保存しました: {filepath}")
    return filepath


def build_adaptive_card(report: WeeklyReport) -> dict:
    """Microsoft Teams用のAdaptive Card JSONを構築する"""
    body_elements = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": report.report_title,
            "wrap": True
        },
        {
            "type": "TextBlock",
            "spacing": "None",
            "isSubtle": True,
            "text": f"対象: {report.company_name} | {report.generated_at}",
            "wrap": True
        },
        {
            "type": "Container",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "weight": "Bolder",
                    "text": "💡 今週のマクロトレンド & 総括"
                },
                {
                    "type": "TextBlock",
                    "text": report.overall_trend_comment,
                    "wrap": True
                }
            ]
        }
    ]

    for idx, idea in enumerate(report.ideas, 1):
        idea_card = {
            "type": "Container",
            "separator": True,
            "items": [
                {
                    "type": "TextBlock",
                    "size": "Medium",
                    "weight": "Bolder",
                    "color": "Accent",
                    "text": f"🚀 アイデア {idx}: {idea.article_title}",
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "記事要約", "value": idea.source_summary},
                        {"title": "課題(Pain)", "value": idea.market_pain},
                        {"title": "最新技術", "value": idea.latest_tech},
                        {"title": "事業アイデア", "value": idea.solution_idea},
                        {"title": "マネタイズ", "value": idea.monetization_model},
                        {"title": "自社の打ち手", "value": idea.internal_next_action}
                    ]
                },
                {
                    "type": "ActionSet",
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "元記事を読む ↗",
                            "url": idea.article_url
                        }
                    ]
                }
            ]
        }
        body_elements.append(idea_card)

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body_elements
                }
            }
        ]
    }
    return payload


def send_to_teams(webhook_url: str, report: WeeklyReport) -> bool:
    """TeamsのIncoming Webhookにレポートを送信する"""
    if not webhook_url or "your_teams_webhook_url" in webhook_url:
        logger.warning("Teams Webhook URLが設定されていないため、Teams送信をスキップします。")
        return False

    payload = build_adaptive_card(report)
    headers = {"Content-Type": "application/json"}

    try:
        logger.info("Teamsへレポートを送信中...")
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
        if resp.status_code in [200, 202]:
            logger.info("Teamsへの送信が成功しました。")
            return True
        else:
            logger.warning(f"Teams送信で非200レスポンスを受信しました ({resp.status_code}): {resp.text}")
            # 旧コネクタ形式にフォールバックして再送を試みる
            fallback_payload = {
                "text": format_report_to_markdown(report)
            }
            fb_resp = requests.post(webhook_url, json=fallback_payload, headers=headers, timeout=15)
            if fb_resp.status_code in [200, 202]:
                logger.info("フォールバック形式でTeamsへの送信が成功しました。")
                return True
            else:
                logger.error(f"フォールバック送信も失敗しました ({fb_resp.status_code}): {fb_resp.text}")
                return False
    except Exception as e:
        logger.error(f"Teamsへの送信中にエラーが発生しました: {e}")
        return False
