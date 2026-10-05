import os
import json
import logging
from datetime import datetime

from typing import Any

try:
    from models import WeeklyReport
except Exception:
    WeeklyReport = Any

logger = logging.getLogger(__name__)

REPORTS_DIR = "reports"


def _score_stars(score: int) -> str:
    s = max(1, min(5, score or 3))
    return "★" * s + "☆" * (5 - s)


def _score_bar(score: int, max_val: int = 5) -> str:
    s = max(1, min(max_val, score or 3))
    filled = "█" * (s * 2)
    empty = "░" * ((max_val - s) * 2)
    return f"[{filled}{empty}] {s}/{max_val}"


def _verdict_badge(verdict: str) -> str:
    v = verdict or ""
    if "即座" in v or "即着手" in v:
        return "🟢 **即座に着手**"
    elif "限定" in v:
        return "🟡 **限定検証**"
    elif "見送り" in v:
        return "🔴 **見送り**"
    return f"⚖️ **{v[:15]}**"


def _recommended_action(impact: int, feasibility: int) -> str:
    if impact >= 4 and feasibility >= 4:
        return "🚀 **クイックウィン (最優先で即着手)**"
    elif impact >= 4 and feasibility <= 3:
        return "🎯 **戦略的投資 (PoCで段階検証)**"
    elif impact <= 3 and feasibility >= 4:
        return "⚡ **低リスク改善 (余力で実施)**"
    else:
        return "🔍 **要再検討 / 見送り**"


def format_report_to_markdown(report: Any) -> str:
    """レポートを読みやすいMarkdown形式（表やグラフ・スコアゲージ満載）にフォーマットする"""
    md = f"# {report.report_title}\n\n"
    kpi_meta = f" | **🎯 重点KPI:** {report.focus_kpi}" if report.focus_kpi else ""
    md += f"**対象部門/企業:** {report.company_name} | **生成日:** {report.generated_at}{kpi_meta}\n\n"

    # 自社課題起点リサーチフォーカス
    issue_summary = getattr(report, "issue_research_summary", None)
    if issue_summary:
        md += f"> 🎯 **自社課題逆引きリサーチ:** {issue_summary}\n\n"
    
    md += "## 💡 今週のマクロトレンド & 総括\n"
    md += f"{report.overall_trend_comment}\n\n"
    md += "---\n\n"

    # =========================================================================
    # 1. エグゼクティブ・サマリー比較表 (全アイデア一覧)
    # =========================================================================
    if report.ideas:
        md += "## 📊 【エグゼクティブ比較表】今週の事業アイデア一覧\n\n"
        md += "| No. | アイデア企画名 | 着想元 | KPIインパクト | 実現容易性 | スピード | 市場規模 | 参謀判定 |\n"
        md += "|:---:|:---|:---|:---:|:---:|:---:|:---:|:---|\n"
        for idx, idea in enumerate(report.ideas, 1):
            title = getattr(idea, "idea_title", None) or getattr(idea, "article_title", "") or f"アイデア {idx}"
            is_breakthrough = getattr(idea, "is_issue_driven_breakthrough", False)
            title_prefix = "🎯 " if is_breakthrough else ""
            
            global_tag = "🇺🇸海外" if getattr(idea, "is_global", False) else "🇯🇵国内"
            source_arts = getattr(idea, "source_articles", [])
            if source_arts:
                sources_str = ", ".join([f"{'🎯' if getattr(a, 'is_issue_driven', False) else ('🇺🇸' if a.is_global else '🇯🇵')}{a.source or 'メディア'}" for a in source_arts[:2]])
            else:
                sources_str = "🎯逆引き" if is_breakthrough else global_tag

            imp = getattr(idea, "impact_score", 4)
            fea = getattr(idea, "feasibility_score", 3)
            spd = getattr(idea, "speed_score", 3)
            mkt = getattr(idea, "target_market_size", "中")
            vrd = _verdict_badge(getattr(idea, "objective_verdict", ""))

            md += f"| **{idx}** | **{title_prefix}{title}** | {sources_str} | {_score_stars(imp)} | {_score_stars(fea)} | {_score_stars(spd)} | {mkt} | {vrd} |\n"
        md += "\n"

        # =========================================================================
        # 2. ポジショニング & 評価マトリクス (インパクト × 実現性チャート)
        # =========================================================================
        md += "### 📈 アイデア評価マトリクス (インパクト × 実現容易性)\n\n"
        md += "| No. | アイデア企画名 | 🎯 KPIインパクト | ⚡ 実現容易性 | ⏱️ 検証スピード | 📌 推奨アクション |\n"
        md += "|:---:|:---|:---|:---|:---|:---|\n"
        for idx, idea in enumerate(report.ideas, 1):
            title = getattr(idea, "idea_title", None) or getattr(idea, "article_title", "") or f"アイデア {idx}"
            is_breakthrough = getattr(idea, "is_issue_driven_breakthrough", False)
            title_prefix = "🎯 " if is_breakthrough else ""
            imp = getattr(idea, "impact_score", 4)
            fea = getattr(idea, "feasibility_score", 3)
            spd = getattr(idea, "speed_score", 3)
            act = _recommended_action(imp, fea)
            md += f"| **{idx}** | **{title_prefix}{title}** | `{_score_bar(imp)}` | `{_score_bar(fea)}` | `{_score_bar(spd)}` | {act} |\n"
        md += "\n---\n\n"

    # =========================================================================
    # 3. 各アイデアの詳細分析 (表とフロー図で視覚化)
    # =========================================================================
    for idx, idea in enumerate(report.ideas, 1):
        idea_title = getattr(idea, "idea_title", None) or getattr(idea, "article_title", "") or f"事業アイデア {idx}"
        is_breakthrough = getattr(idea, "is_issue_driven_breakthrough", False)
        breakthrough_badge = " [🎯 自社課題突破案]" if is_breakthrough else ""
        global_badge = " [🇺🇸 海外先行事例]" if getattr(idea, "is_global", False) and not is_breakthrough else ""
        md += f"## 🚀 アイデア {idx}: {idea_title}{breakthrough_badge}{global_badge}\n\n"

        # スコアカード
        imp = getattr(idea, "impact_score", 4)
        fea = getattr(idea, "feasibility_score", 3)
        spd = getattr(idea, "speed_score", 3)
        mkt = getattr(idea, "target_market_size", "中")
        md += f"> **【定量スコア】** 🎯 **インパクト:** `{_score_bar(imp)}` | ⚡ **実現容易性:** `{_score_bar(fea)}` | ⏱️ **検証スピード:** `{_score_bar(spd)}` | 🏢 **市場規模:** `{mkt}`\n\n"

        # 解決対象の切実な課題
        addressed_issue = getattr(idea, "addressed_issue", None)
        if addressed_issue:
            md += f"> 🎯 **解決を狙う自社の切実な課題:** **{addressed_issue}**\n\n"

        # 複数記事の参照情報
        source_arts = getattr(idea, "source_articles", [])
        if source_arts:
            md += "### 📰 着想元となった複数記事 & 先行事例\n"
            for a in source_arts:
                if getattr(a, "is_issue_driven", False):
                    g_tag = "[🎯 課題逆引き]"
                elif getattr(a, "is_global", False):
                    g_tag = "[🇺🇸 海外]"
                else:
                    g_tag = "[🇯🇵 国内]"
                src_info = f" (出所: {a.source})" if getattr(a, "source", "") else ""
                md += f"- **{g_tag} [{a.title}]({a.url})**{src_info}\n"
                if getattr(a, "summary", ""):
                    md += f"  > 要約: {a.summary}\n"
            md += "\n"
        else:
            md += f"- **元記事リンク:** [{idea.article_title}]({idea.article_url})\n"
            md += f"- **記事の要約:** {idea.source_summary}\n\n"

        # シナジー背景
        synergy = getattr(idea, "synergy_rationale", "")
        if synergy:
            md += f"### 🔗 複数記事の掛け合わせ・シナジー背景 (Connecting the Dots)\n> {synergy}\n\n"

        if getattr(idea, "researched_facts", None):
            md += f"- **🔍 市場背景・競合動向 (Webリサーチ):**\n  > {idea.researched_facts}\n\n"
        if getattr(idea, "localization_opportunity", None):
            md += f"- **🌐 日本市場へのローカライズ機会 (タイムマシン経営):**\n  > {idea.localization_opportunity}\n\n"

        # 事業創出フロー図
        md += "### 🔄 事業創出フロー\n"
        md += f"```text\n"
        md += f"【顧客の課題 (Pain)】 {idea.market_pain[:45]}...\n"
        md += f"       ▼\n"
        md += f"【AIソリューション】  {idea.solution_idea[:45]}...\n"
        md += f"       ▼\n"
        md += f"【成果 & KPI達成】   {idea.kpi_impact[:45]}...\n"
        md += f"```\n\n"

        # 攻めの事業企画 (表形式)
        md += "### 💡 攻めの事業企画 (Solution & Monetization)\n\n"
        md += "| 項目 | 内容・仕様 |\n"
        md += "|:---|:---|\n"
        md += f"| 💥 **世の中の課題 (Pain)** | {idea.market_pain} |\n"
        md += f"| ⚙️ **活用技術 (Tech)** | {idea.latest_tech} |\n"
        md += f"| 💡 **解決・事業化案** | **{idea.solution_idea}** |\n"
        md += f"| 💰 **マネタイズモデル** | {idea.monetization_model} |\n"
        md += f"| 🎯 **自社KPIへの貢献** | **{idea.kpi_impact}** |\n"
        md += f"| 🚀 **自社での最初の打ち手** | `{idea.internal_next_action}` |\n"
        if getattr(idea, "required_resources", None):
            md += f"| 🛠️ **推奨PoCリソース** | `{idea.required_resources}` |\n"
        if getattr(idea, "resource_fit_note", None):
            md += f"| 🧩 **リソース適合性** | {idea.resource_fit_note} |\n"
        md += "\n"

        # 守り・リスク評価 (表形式)
        md += "### 🛡️ 守り・リスク評価 (Critical Defense & Risk)\n\n"
        md += "| 評価軸 | 参謀の冷徹判定・分析 |\n"
        md += "|:---|:---|\n"
        md += f"| ⚡ **実現性・難易度** | {idea.feasibility_rating} ({_score_stars(fea)}) |\n"
        md += f"| ⚠️ **最大の盲点・参入障壁** | {idea.critical_risks} |\n"
        md += f"| 👥 **顧客受容性・導入障壁** | {idea.customer_readiness} |\n"
        md += f"| ⚖️ **客観的参謀の辛口ジャッジ** | {_verdict_badge(idea.objective_verdict)}<br>*{idea.objective_verdict}* |\n\n"

        md += "---\n\n"

    return md


def format_report_to_html(report: WeeklyReport) -> str:
    """メール用のリッチで美しいHTML本文を生成する（グラフバー・表満載）"""
    # 比較サマリー表の行HTML
    summary_rows_html = ""
    for idx, idea in enumerate(report.ideas, 1):
        idea_title = getattr(idea, "idea_title", None) or getattr(idea, "article_title", "") or f"アイデア {idx}"
        is_global = getattr(idea, "is_global", False)
        g_badge = '<span style="background-color: #5c2d91; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 4px;">🇺🇸海外</span>' if is_global else '<span style="background-color: #0078d4; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 4px;">🇯🇵国内</span>'
        imp = getattr(idea, "impact_score", 4)
        fea = getattr(idea, "feasibility_score", 3)
        spd = getattr(idea, "speed_score", 3)
        vrd = getattr(idea, "objective_verdict", "")
        vrd_color = "#107c41" if ("即座" in vrd or "即着手" in vrd) else ("#d83b01" if "見送り" in vrd else "#0078d4")

        summary_rows_html += f"""
        <tr style="border-bottom: 1px solid #edebe9; font-size: 13px;">
            <td style="padding: 10px 8px; text-align: center; font-weight: bold; color: #0078d4;">#{idx}</td>
            <td style="padding: 10px 8px; font-weight: bold; color: #323130;">{g_badge} {idea_title}</td>
            <td style="padding: 10px 8px; text-align: center; color: #d83b01; font-weight: bold;">{_score_stars(imp)}</td>
            <td style="padding: 10px 8px; text-align: center; color: #0078d4; font-weight: bold;">{_score_stars(fea)}</td>
            <td style="padding: 10px 8px; text-align: center; color: #107c41; font-weight: bold;">{_score_stars(spd)}</td>
            <td style="padding: 10px 8px; font-size: 12px; color: {vrd_color}; font-weight: bold;">{vrd[:20]}</td>
        </tr>
        """

    ideas_html = ""
    for idx, idea in enumerate(report.ideas, 1):
        idea_title = getattr(idea, "idea_title", None) or getattr(idea, "article_title", "") or f"事業アイデア {idx}"
        is_breakthrough = getattr(idea, "is_issue_driven_breakthrough", False)
        is_global = getattr(idea, "is_global", False)
        
        breakthrough_badge = '<span style="background-color: #0b57d0; color: #ffffff; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 10px; margin-left: 8px; vertical-align: middle;">🎯 課題逆引き突破案</span>' if is_breakthrough else ''
        global_badge = '<span style="background-color: #5c2d91; color: #ffffff; font-size: 11px; font-weight: normal; padding: 2px 8px; border-radius: 10px; margin-left: 8px; vertical-align: middle;">🇺🇸 海外先行事例</span>' if (is_global and not is_breakthrough) else ''

        imp = getattr(idea, "impact_score", 4)
        fea = getattr(idea, "feasibility_score", 3)
        spd = getattr(idea, "speed_score", 3)
        mkt = getattr(idea, "target_market_size", "中")

        # スコアバーメーターHTML
        score_meters_html = f"""
        <div style="background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 14px 18px; margin-bottom: 16px;">
            <div style="font-weight: bold; font-size: 13px; color: #495057; margin-bottom: 10px;">📊 定量スコア・評価メーター</div>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <tr>
                    <td style="width: 25%; color: #d83b01; font-weight: bold;">🎯 自社KPIインパクト</td>
                    <td style="width: 25%;">
                        <div style="background-color: #edebe9; border-radius: 4px; height: 10px; overflow: hidden; width: 100%;">
                            <div style="background-color: #d83b01; height: 100%; width: {imp * 20}%;"></div>
                        </div>
                    </td>
                    <td style="width: 25%; padding-left: 15px; color: #0078d4; font-weight: bold;">⚡ 実現容易性</td>
                    <td style="width: 25%;">
                        <div style="background-color: #edebe9; border-radius: 4px; height: 10px; overflow: hidden; width: 100%;">
                            <div style="background-color: #0078d4; height: 100%; width: {fea * 20}%;"></div>
                        </div>
                    </td>
                </tr>
                <tr>
                    <td style="color: #107c41; font-weight: bold; padding-top: 8px;">⏱️ 検証スピード</td>
                    <td style="padding-top: 8px;">
                        <div style="background-color: #edebe9; border-radius: 4px; height: 10px; overflow: hidden; width: 100%;">
                            <div style="background-color: #107c41; height: 100%; width: {spd * 20}%;"></div>
                        </div>
                    </td>
                    <td style="padding-left: 15px; color: #5c2d91; font-weight: bold; padding-top: 8px;">🏢 想定市場規模</td>
                    <td style="padding-top: 8px; font-weight: bold; color: #5c2d91;">
                        {mkt}
                    </td>
                </tr>
            </table>
        </div>
        """

        # 複数記事の参照リスト
        source_arts = getattr(idea, "source_articles", [])
        if source_arts:
            articles_html_list = ""
            for a in source_arts:
                a_global = '<span style="background-color: #5c2d91; color: #ffffff; font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-right: 4px;">🇺🇸海外</span>' if getattr(a, "is_global", False) else '<span style="background-color: #0078d4; color: #ffffff; font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-right: 4px;">🇯🇵国内</span>'
                src_txt = f" ({a.source})" if getattr(a, "source", "") else ""
                sum_txt = f"<div style='font-size: 12px; color: #605e5c; margin-top: 2px;'>{a.summary}</div>" if getattr(a, "summary", "") else ""
                articles_html_list += f"""
                <li style="margin-bottom: 8px; font-size: 13px;">
                    {a_global} <strong><a href="{a.url}" target="_blank" style="color: #0078d4; text-decoration: none;">{a.title}</a></strong>{src_txt}
                    {sum_txt}
                </li>
                """
            sources_box = f"""
            <div style="background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 12px 16px; margin-bottom: 14px;">
                <div style="font-weight: bold; font-size: 13px; color: #495057; margin-bottom: 6px;">📰 着想元となった複数記事・動向:</div>
                <ul style="margin: 0; padding-left: 18px; color: #323130;">
                    {articles_html_list}
                </ul>
            </div>
            """
        else:
            sources_box = f"""
            <p style="font-size: 13px; color: #605e5c; margin-bottom: 12px;">
                <strong>📰 元記事:</strong> <a href="{idea.article_url}" target="_blank" style="color: #0078d4; text-decoration: none;">{idea.article_title} ↗</a>
            </p>
            <div style="background-color: #f3f2f1; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 14px; line-height: 1.5;">
                <strong>記事のファクト要約:</strong> {idea.source_summary}
            </div>
            """

        # シナジー背景
        synergy_box = ""
        synergy = getattr(idea, "synergy_rationale", "")
        if synergy:
            synergy_box = f"""
            <div style="background: linear-gradient(135deg, #f3e8ff, #ede9fe); border-left: 4px solid #7c3aed; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 14px; font-size: 13px; line-height: 1.6; color: #5b21b6;">
                <strong>🔗 複数記事の掛け合わせ背景 (Connecting the Dots):</strong><br>
                <span style="color: #1e1b4b;">{synergy}</span>
            </div>
            """

        researched_box = ""
        if getattr(idea, "researched_facts", None):
            researched_box = f"""
            <div style="background-color: #f0f7ff; border-left: 4px solid #0078d4; padding: 10px 14px; border-radius: 0 4px 4px 0; margin-bottom: 12px; font-size: 13px; line-height: 1.5; color: #106ebe;">
                <strong>🔍 市場背景・競合リサーチ (Web検索):</strong><br>
                <span style="color: #201f1e;">{idea.researched_facts}</span>
            </div>
            """

        localization_box = ""
        if getattr(idea, "localization_opportunity", None):
            localization_box = f"""
            <div style="background-color: #f5f0fb; border-left: 4px solid #5c2d91; padding: 10px 14px; border-radius: 0 4px 4px 0; margin-bottom: 12px; font-size: 13px; line-height: 1.5; color: #5c2d91;">
                <strong>🌐 日本市場へのローカライズ機会 (タイムマシン経営):</strong><br>
                <span style="color: #201f1e;">{idea.localization_opportunity}</span>
            </div>
            """

        # 課題 ➔ 解決 ➔ 成果のフロー
        flow_box = f"""
        <div style="display: flex; justify-content: space-between; background-color: #f0f4f8; border-radius: 6px; padding: 12px; margin-bottom: 16px; font-size: 12px; text-align: center;">
            <div style="width: 30%; background-color: #fff; padding: 8px; border-radius: 4px; border-left: 3px solid #d83b01;">
                <strong style="color: #d83b01;">💥 顧客の課題</strong><br>{idea.market_pain[:30]}...
            </div>
            <div style="display: flex; align-items: center; color: #8a8886; font-size: 16px;">➔</div>
            <div style="width: 30%; background-color: #fff; padding: 8px; border-radius: 4px; border-left: 3px solid #0078d4;">
                <strong style="color: #0078d4;">💡 AI解決案</strong><br>{idea.solution_idea[:30]}...
            </div>
            <div style="display: flex; align-items: center; color: #8a8886; font-size: 16px;">➔</div>
            <div style="width: 30%; background-color: #fff; padding: 8px; border-radius: 4px; border-left: 3px solid #107c41;">
                <strong style="color: #107c41;">🎯 KPI達成</strong><br>{idea.kpi_impact[:30]}...
            </div>
        </div>
        """

        addressed_issue_box = ""
        addressed_issue = getattr(idea, "addressed_issue", None)
        if addressed_issue:
            addressed_issue_box = f"""
            <div style="background-color: #eef2ff; border-left: 4px solid #4f46e5; padding: 10px 14px; border-radius: 0 4px 4px 0; margin-bottom: 12px; font-size: 13px; line-height: 1.5; color: #3730a3;">
                <strong>🎯 解決を狙う自社の切実な課題:</strong> <strong>{addressed_issue}</strong>
            </div>
            """

        ideas_html += f"""
        <div style="margin-bottom: 30px; padding: 22px; background-color: #ffffff; border: 1px solid #e1dfdd; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.06);">
            <h3 style="margin-top: 0; color: #0078d4; font-size: 18px; border-bottom: 2px solid #0078d4; padding-bottom: 8px;">
                🚀 アイデア {idx}: {idea_title} {breakthrough_badge}{global_badge}
            </h3>
            {score_meters_html}
            {addressed_issue_box}
            {flow_box}
            {sources_box}
            {synergy_box}
            {researched_box}
            {localization_box}

            <h4 style="margin: 16px 0 8px 0; font-size: 15px; color: #106ebe; border-bottom: 1px dashed #c8c6c4; padding-bottom: 4px;">
                💡 攻めの事業企画スペック表
            </h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.6; margin-bottom: 16px;">
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="width: 25%; font-weight: bold; color: #d83b01; padding: 8px 6px; vertical-align: top; background-color: #fffaf9;">
                        💥 課題 (Pain)
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.market_pain}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #107c41; padding: 8px 6px; vertical-align: top; background-color: #f7fdf9;">
                        ⚙️ 最新技術 (Tech)
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.latest_tech}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #0078d4; padding: 8px 6px; vertical-align: top; background-color: #f5faff;">
                        💡 解決・事業案
                    </td>
                    <td style="padding: 8px 6px; color: #323130; font-weight: bold;">
                        {idea.solution_idea}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #8764b8; padding: 8px 6px; vertical-align: top; background-color: #faf7fd;">
                        💰 マネタイズ
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.monetization_model}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #d83b01; padding: 8px 6px; vertical-align: top; background-color: #fffaf9;">
                        🎯 KPI貢献
                    </td>
                    <td style="padding: 8px 6px; color: #323130; font-weight: bold;">
                        {idea.kpi_impact}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #004e8c; padding: 8px 6px; vertical-align: top; background-color: #f0f7ff;">
                        🚀 自社の打ち手
                    </td>
                    <td style="padding: 8px 6px; color: #323130; background-color: #f0f7ff; border-radius: 4px; font-weight: bold;">
                        {idea.internal_next_action}
                    </td>
                </tr>
                {f'''<tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #b14700; padding: 8px 6px; vertical-align: top; background-color: #fffaf0;">
                        🛠️ 推奨PoCリソース
                    </td>
                    <td style="padding: 8px 6px; color: #323130; font-weight: bold;">
                        {idea.required_resources}
                    </td>
                </tr>''' if getattr(idea, "required_resources", None) else ''}
                {f'''<tr>
                    <td style="font-weight: bold; color: #498205; padding: 8px 6px; vertical-align: top; background-color: #f8fbf5;">
                        🧩 リソース適合性
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.resource_fit_note}
                    </td>
                </tr>''' if getattr(idea, "resource_fit_note", None) else ''}
            </table>

            <h4 style="margin: 16px 0 8px 0; font-size: 15px; color: #a80000; border-bottom: 1px dashed #c8c6c4; padding-bottom: 4px;">
                🛡️ 守り・リスク評価マトリクス表
            </h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.6;">
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="width: 25%; font-weight: bold; color: #5c2d91; padding: 8px 6px; vertical-align: top; background-color: #faf7fd;">
                        ⚡ 実現性・難易度
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.feasibility_rating} ({_score_stars(fea)})
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #a80000; padding: 8px 6px; vertical-align: top; background-color: #fff5f5;">
                        ⚠️ 最大の盲点・障壁
                    </td>
                    <td style="padding: 8px 6px; color: #323130; background-color: #fff8f8;">
                        {idea.critical_risks}
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f3f2f1;">
                    <td style="font-weight: bold; color: #498205; padding: 8px 6px; vertical-align: top; background-color: #f8fbf5;">
                        👥 顧客の受容性
                    </td>
                    <td style="padding: 8px 6px; color: #323130;">
                        {idea.customer_readiness}
                    </td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #004b50; padding: 8px 6px; vertical-align: top; background-color: #f4fafb;">
                        ⚖️ 参謀の辛口ジャッジ
                    </td>
                    <td style="padding: 8px 6px; color: #201f1e; background-color: #f6f8fa; font-weight: bold; border-left: 3px solid #004b50;">
                        {idea.objective_verdict}
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
        <div style="max-width: 820px; margin: 0 auto;">
            <!-- ヘッダー -->
            <div style="background: linear-gradient(135deg, #0078d4, #106ebe); color: #ffffff; padding: 24px; border-radius: 8px; margin-bottom: 20px;">
                <h1 style="margin: 0 0 8px 0; font-size: 22px;">{report.report_title}</h1>
                <p style="margin: 0; font-size: 13px; opacity: 0.9;">
                    対象: {report.company_name} | 発行日: {report.generated_at}{f' | 🎯 重点KPI: {report.focus_kpi}' if report.focus_kpi else ''}
                </p>
            </div>

            {f'''<div style="background-color: #eef2ff; border-left: 5px solid #4f46e5; padding: 14px 18px; border-radius: 4px; margin-bottom: 20px; font-size: 13px; color: #3730a3; line-height: 1.5;">
                <strong>🎯 自社課題逆引きリサーチ:</strong> {getattr(report, "issue_research_summary", "")}
            </div>''' if getattr(report, "issue_research_summary", None) else ''}

            <!-- 総括ハイライト -->
            <div style="background-color: #e8f4fc; border-left: 5px solid #0078d4; padding: 16px 20px; border-radius: 4px; margin-bottom: 25px;">
                <h3 style="margin-top: 0; margin-bottom: 8px; color: #004e8c; font-size: 16px;">
                    💡 今週のマクロトレンド & 総括
                </h3>
                <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #201f1e;">
                    {report.overall_trend_comment}
                </p>
            </div>

            <!-- エグゼクティブ・サマリー比較表 -->
            <div style="background-color: #ffffff; border: 1px solid #e1dfdd; border-radius: 8px; padding: 20px; margin-bottom: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.06);">
                <h3 style="margin-top: 0; margin-bottom: 12px; color: #0078d4; font-size: 16px; border-bottom: 2px solid #0078d4; padding-bottom: 6px;">
                    📊 【エグゼクティブ比較表】今週の全アイデア一覧
                </h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #f3f2f1; font-size: 12px; color: #605e5c; text-align: left; border-bottom: 2px solid #e1dfdd;">
                            <th style="padding: 8px; text-align: center;">No</th>
                            <th style="padding: 8px;">アイデア名</th>
                            <th style="padding: 8px; text-align: center;">KPIインパクト</th>
                            <th style="padding: 8px; text-align: center;">実現容易性</th>
                            <th style="padding: 8px; text-align: center;">スピード</th>
                            <th style="padding: 8px;">参謀ジャッジ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {summary_rows_html}
                    </tbody>
                </table>
            </div>

            <!-- アイデア一覧 -->
            {ideas_html}

            <!-- フッター -->
            <div style="text-align: center; font-size: 12px; color: #a19f9d; margin-top: 30px; border-top: 1px solid #edebe9; padding-top: 15px;">
                本レポートはビジネス成長AIエージェントにより自動生成されました。
            </div>
        </div>
    </body>
    </html>
    """
    return html


def save_markdown_report(report: WeeklyReport) -> str:
    """レポートをローカルファイル（Markdown および JSON）に保存する"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"growth_report_{timestamp}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    content = format_report_to_markdown(report)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # Web UIや再利用向けに構造化JSONも同名で保存
    json_filepath = os.path.join(REPORTS_DIR, f"growth_report_{timestamp}.json")
    try:
        with open(json_filepath, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
    except Exception as e:
        logger.warning(f"JSONレポートの保存に失敗しました: {e}")

    logger.info(f"レポートを保存しました: {filepath}")
    return filepath


def load_report_data(report_id: str) -> dict:
    """指定されたレポートIDの構造化データとMarkdownを取得する"""
    json_path = os.path.join(REPORTS_DIR, f"{report_id}.json")
    md_path = os.path.join(REPORTS_DIR, f"{report_id}.md")

    data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
            # WeeklyReportモデルを通してスコアの自動計算・補完を反映
            try:
                model_obj = WeeklyReport(**raw_json)
                data = model_obj.model_dump()
            except Exception:
                data = raw_json
        except Exception as e:
            logger.warning(f"JSON読み込み失敗: {e}")

    raw_markdown = ""
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            raw_markdown = f.read()

    data["raw_markdown"] = raw_markdown
    data["report_id"] = report_id
    return data


def list_saved_reports() -> list:
    """保存された全レポートの一覧をメタデータ付きで取得する（新しい順）"""
    if not os.path.exists(REPORTS_DIR):
        return []

    files = os.listdir(REPORTS_DIR)
    reports = []
    seen_ids = set()

    for f in sorted(files, reverse=True):
        if f.endswith(".json") or f.endswith(".md"):
            rep_id = os.path.splitext(f)[0]
            if rep_id in seen_ids or rep_id == ".gitkeep":
                continue
            seen_ids.add(rep_id)

            item = {
                "id": rep_id,
                "created_at": rep_id.replace("growth_report_", "").replace("bizdev_report_", ""),
                "title": "週次ビジネス成長レポート",
                "focus_kpi": None,
                "company_name": "",
                "idea_count": 0,
                "macro_trend": "",
                "has_json": os.path.exists(os.path.join(REPORTS_DIR, f"{rep_id}.json")),
                "has_md": os.path.exists(os.path.join(REPORTS_DIR, f"{rep_id}.md")),
            }

            # JSONがあれば詳細メタデータを吸い出す
            if item["has_json"]:
                try:
                    with open(os.path.join(REPORTS_DIR, f"{rep_id}.json"), "r", encoding="utf-8") as jf:
                        jdata = json.load(jf)
                        item["title"] = jdata.get("report_title", item["title"])
                        item["focus_kpi"] = jdata.get("focus_kpi")
                        item["company_name"] = jdata.get("company_name", "")
                        item["macro_trend"] = jdata.get("overall_trend_comment", "")
                        item["idea_count"] = len(jdata.get("ideas", []))
                        if "generated_at" in jdata:
                            item["created_at"] = jdata["generated_at"]
                except Exception:
                    pass
            elif item["has_md"]:
                # Markdownからタイトルを簡易抽出
                try:
                    with open(os.path.join(REPORTS_DIR, f"{rep_id}.md"), "r", encoding="utf-8") as mf:
                        first_line = mf.readline().strip().lstrip("#").strip()
                        if first_line:
                            item["title"] = first_line
                except Exception:
                    pass

            reports.append(item)

    return reports


def send_via_gmail(
    report: WeeklyReport,
    gmail_user: str,
    gmail_password: str,
    to_email: str
) -> bool:
    """
    GmailのSMTPサーバー経由でリッチHTMLメールを送信する
    Mac、Windows、Linux、GitHub Actions問わず動作します。
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not gmail_user or not gmail_password:
        logger.error("Gmailの認証情報（GMAIL_USER または GMAIL_APP_PASSWORD）が設定されていません。")
        return False

    if not to_email:
        to_email = gmail_user

    try:
        logger.info(f"Gmail経由でメールを送信中... (送信元: {gmail_user}, 宛先: {to_email})")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = report.report_title
        msg["From"] = f"ビジネス成長AI参謀 <{gmail_user}>"
        msg["To"] = to_email

        # プレーンテキスト版とHTML版を添付
        text_part = MIMEText(format_report_to_markdown(report), "plain", "utf-8")
        html_part = MIMEText(format_report_to_html(report), "html", "utf-8")
        msg.attach(text_part)
        msg.attach(html_part)

        # smtp.gmail.com:587 (STARTTLS)
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [to_email], msg.as_string())

        logger.info("Gmailからのメール送信が正常に完了しました！")
        return True
    except Exception as e:
        logger.error(f"Gmail送信中にエラーが発生しました: {e}")
        return False


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
        idea_title = getattr(idea, "idea_title", None) or idea.article_title or f"事業アイデア {idx}"
        is_global = getattr(idea, "is_global", False)
        global_tag = "[🇺🇸海外] " if is_global else ""
        source_arts = getattr(idea, "source_articles", [])
        synergy = getattr(idea, "synergy_rationale", "")

        facts = []
        if source_arts:
            src_titles = " / ".join([a.title[:30] + "..." for a in source_arts[:3]])
            facts.append({"title": "📰着想元記事", "value": src_titles})
        else:
            facts.append({"title": "記事要約", "value": idea.source_summary or ""})

        if synergy:
            facts.append({"title": "🔗シナジー背景", "value": synergy})
        if getattr(idea, "researched_facts", None):
            facts.append({"title": "市場/競合リサーチ", "value": idea.researched_facts})
        if getattr(idea, "localization_opportunity", None):
            facts.append({"title": "🌐ローカライズ", "value": idea.localization_opportunity})

        facts.extend([
            {"title": "課題(Pain)", "value": idea.market_pain},
            {"title": "最新技術", "value": idea.latest_tech},
            {"title": "事業アイデア", "value": idea.solution_idea},
            {"title": "マネタイズ", "value": idea.monetization_model},
            {"title": "🎯KPI貢献", "value": idea.kpi_impact},
            {"title": "自社の打ち手", "value": idea.internal_next_action},
            {"title": "🛠️PoCリソース", "value": getattr(idea, "required_resources", None) or "標準"},
            {"title": "🧩適合理由", "value": getattr(idea, "resource_fit_note", None) or "自社体制で検証可"},
            {"title": "⚡実現性/難易度", "value": idea.feasibility_rating},
            {"title": "⚠️最大リスク/障壁", "value": idea.critical_risks},
            {"title": "👥顧客受容性", "value": idea.customer_readiness},
            {"title": "⚖️参謀判定", "value": idea.objective_verdict}
        ])

        actions = []
        if source_arts:
            for a_idx, a in enumerate(source_arts[:2], 1):
                actions.append({
                    "type": "Action.OpenUrl",
                    "title": f"記事{a_idx}: {a.title[:15]}... ↗",
                    "url": a.url
                })
        elif idea.article_url:
            actions.append({
                "type": "Action.OpenUrl",
                "title": "元記事を読む ↗",
                "url": idea.article_url
            })

        idea_card = {
            "type": "Container",
            "separator": True,
            "items": [
                {
                    "type": "TextBlock",
                    "size": "Medium",
                    "weight": "Bolder",
                    "color": "Accent",
                    "text": f"🚀 アイデア {idx}: {global_tag}{idea_title}",
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": facts
                }
            ] + ([{"type": "ActionSet", "actions": actions}] if actions else [])
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


def send_to_teams(webhook_url: str, report) -> bool:
    """TeamsのIncoming Webhookにレポートを送信する（チャネルまたはチャット宛て）"""
    if not webhook_url or "your_teams_webhook_url" in webhook_url:
        logger.warning("Teams Webhook URLが設定されていないため、Teams送信をスキップします。")
        return False

    try:
        import requests
    except ImportError:
        logger.error("Teams送信には requests パッケージが必要です ('pip install requests')。")
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
