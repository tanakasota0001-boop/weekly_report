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


def format_report_to_html(report: WeeklyReport) -> str:
    """Outlookメール用のリッチで美しいHTMLメール本文を生成する"""
    ideas_html = ""
    for idx, idea in enumerate(report.ideas, 1):
        ideas_html += f"""
        <div style="margin-bottom: 25px; padding: 20px; background-color: #ffffff; border: 1px solid #e1dfdd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
            <h3 style="margin-top: 0; color: #0078d4; font-size: 18px; border-bottom: 2px solid #0078d4; padding-bottom: 8px;">
                🚀 アイデア {idx}: {idea.article_title}
            </h3>
            <p style="font-size: 13px; color: #605e5c; margin-bottom: 12px;">
                <strong>📰 元記事:</strong> <a href="{idea.article_url}" target="_blank" style="color: #0078d4; text-decoration: none;">元記事を読む ↗</a>
            </p>
            <div style="background-color: #f3f2f1; padding: 10px 14px; border-radius: 4px; margin-bottom: 16px; font-size: 14px; line-height: 1.5;">
                <strong>記事のファクト要約:</strong> {idea.source_summary}
            </div>

            <table style="width: 100%; border-collapse: collapse; font-size: 14px; line-height: 1.6;">
                <tr>
                    <td style="width: 25%; font-weight: bold; color: #d83b01; padding: 8px 0; vertical-align: top;">
                        💥 課題 (Pain)
                    </td>
                    <td style="padding: 8px 0; color: #323130;">
                        {idea.market_pain}
                    </td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #107c41; padding: 8px 0; vertical-align: top;">
                        ⚙️ 最新技術 (Tech)
                    </td>
                    <td style="padding: 8px 0; color: #323130;">
                        {idea.latest_tech}
                    </td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #0078d4; padding: 8px 0; vertical-align: top;">
                        💡 解決・事業案
                    </td>
                    <td style="padding: 8px 0; color: #323130; font-weight: 500;">
                        {idea.solution_idea}
                    </td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #8764b8; padding: 8px 0; vertical-align: top;">
                        💰 マネタイズ
                    </td>
                    <td style="padding: 8px 0; color: #323130;">
                        {idea.monetization_model}
                    </td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #004e8c; padding: 8px 0; vertical-align: top;">
                        🎯 自社の打ち手
                    </td>
                    <td style="padding: 8px 0; color: #323130; background-color: #f0f7ff; padding: 8px; border-radius: 4px;">
                        {idea.internal_next_action}
                    </td>
                </tr>
            </table>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: 'Segoe UI', Meiryo, 'Hiragino Kaku Gothic ProN', sans-serif; background-color: #faf9f8; color: #323130; margin: 0; padding: 20px;">
        <div style="max-width: 800px; margin: 0 auto;">
            <!-- ヘッダー -->
            <div style="background: linear-gradient(135deg, #0078d4, #106ebe); color: #ffffff; padding: 24px; border-radius: 8px; margin-bottom: 20px;">
                <h1 style="margin: 0 0 8px 0; font-size: 22px;">{report.report_title}</h1>
                <p style="margin: 0; font-size: 13px; opacity: 0.9;">
                    対象: {report.company_name} | 発行日: {report.generated_at}
                </p>
            </div>

            <!-- 総括ハイライト -->
            <div style="background-color: #e8f4fc; border-left: 5px solid #0078d4; padding: 16px 20px; border-radius: 4px; margin-bottom: 25px;">
                <h3 style="margin-top: 0; margin-bottom: 8px; color: #004e8c; font-size: 16px;">
                    💡 今週のマクロトレンド & 総括
                </h3>
                <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #201f1e;">
                    {report.overall_trend_comment}
                </p>
            </div>

            <!-- アイデア一覧 -->
            {ideas_html}

            <!-- フッター -->
            <div style="text-align: center; font-size: 12px; color: #a19f9d; margin-top: 30px; border-top: 1px solid #edebe9; padding-top: 15px;">
                本レポートは事業開発部向けAIエージェントにより自動生成されました。
            </div>
        </div>
    </body>
    </html>
    """
    return html


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


def send_via_outlook(report: WeeklyReport, to_email: str, display_only: bool = False) -> bool:
    """
    Windowsのデスクトップ版Outlookを操作してメールを送信または下書き作成する
    社内の管理者権限やAPI設定が一切不要で動作します。
    """
    if not to_email or "@" not in to_email:
        logger.warning("Outlook宛先メールアドレスが正しく設定されていません。")
        return False

    try:
        import win32com.client
    except ImportError:
        logger.error("pywin32 がインストールされていません。'pip install pywin32' を実行してください。")
        return False

    try:
        logger.info(f"Outlookアプリケーションを起動・接続中... (宛先: {to_email})")
        outlook = win32com.client.Dispatch("Outlook.Application")
        # 0 = olMailItem
        mail = outlook.CreateItem(0)
        mail.To = to_email
        mail.Subject = report.report_title
        mail.HTMLBody = format_report_to_html(report)

        if display_only:
            logger.info("Outlookの下書き画面を表示します（送信は行われません）。")
            mail.Display()
            return True
        else:
            logger.info("Outlook経由でメールを自動送信中...")
            mail.Send()
            logger.info("Outlookからの送信が完了しました！")
            return True
    except Exception as e:
        logger.error(f"Outlookメール送信中にエラーが発生しました: {e}")
        return False


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
    """TeamsのIncoming Webhookにレポートを送信する（チャネルまたはチャット宛て）"""
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
