import json
import logging
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from models import (
    CompanyProfile,
    NewsArticle,
    BizDevIdea,
    ArticleReference,
    WeeklyReport
)
from gemini_helper import generate_with_fallback
from scraper import fetch_article_content

logger = logging.getLogger(__name__)


class MultiArticleReportResponse(BaseModel):
    """複数記事のシナジーから創出された事業アイデア群と総括"""
    ideas: List[BizDevIdea] = Field(description="複数記事を掛け合わせて立案された事業アイデアリスト")
    overall_trend_comment: str = Field(description="今回分析した複数記事群とアイデアから見えるマクロな潮目・トレンド総括コメント")


def evaluate_and_filter_articles(
    client: genai.Client,
    model_name: str,
    articles: List[NewsArticle],
    profile: CompanyProfile,
    top_n: int = 5
) -> List[int]:
    """
    収集したニュース記事一覧を自社プロファイルと照らし合わせ、
    複数記事の掛け合わせ（シナジー創出）に最も適した上位top_n件のインデックスを返す
    """
    if not articles:
        return []

    # 記事リストをテキスト化
    articles_text = ""
    for idx, art in enumerate(articles):
        global_tag = "[🇺🇸海外先行SaaS/動向] " if art.is_global else "[🇯🇵国内ニュース] "
        articles_text += f"[{idx}] {global_tag}タイトル: {art.title} (出所: {art.source})\n要約: {art.summary[:150]}\n\n"

    system_instruction = """
あなたはビジネス成長を牽引するチーフストラテジストです。
多数のニュース記事（国内ニュースおよび海外先行SaaS・プロダクト）の中から、「世の中の切実な課題（ペイン）」や「最新技術の応用」「海外先行モデル」を含み、
【他の記事と掛け合わせることで強力な新規事業・新機軸の種になり得る記事】を厳選してください。
単なる単発リリースではなく、複数の記事を繋ぎ合わせてシナジーを生み出せる良質な記事群を優先してください。
"""

    challenges_text = ""
    if profile.current_challenges:
        kpi = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])
        challenges_text = f"\n【★最優先：自社が今直面している重点課題 & 注力KPI】\n- 重点KPI: {kpi}\n"
        if issues:
            challenges_text += "- 直近の課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

    prompt = f"""
以下の【自社プロファイル】と【ニュース記事一覧（国内＋海外先行事例）】を照合し、
複数記事を掛け合わせて新機軸アイデアを創出するための注目記事を上位{top_n}件選定してください。

【自社プロファイル】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット顧客: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}
{challenges_text}
【選定基準】
1. 自社直近KPIとの合致度: 自社の重点KPIや切実な課題の突破口になり得るか（最優先）
2. シナジー性: 他の記事（国内課題 × 海外先行モデル × 最新AI技術など）と掛け合わせやすいか
3. 課題の深刻度: 世の中や顧客の強いペイン・不満が潜んでいるか
4. 海外モデルのタイムマシン価値: 日本の小規模事業者に輸入・応用できるか

【ニュース記事一覧】
{articles_text}

出力は以下のJSON形式で、上位{top_n}件のインデックス番号の配列のみを出力してください:
{{
  "selected_indices": [0, 2, 4, 7]
}}
"""

    try:
        response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        res_json = json.loads(response.text)
        indices = res_json.get("selected_indices", [])
        valid_indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(articles)]
        return valid_indices[:top_n] if valid_indices else list(range(min(top_n, len(articles))))
    except Exception as e:
        logger.warning(f"記事スクリーニング中にエラーが発生しました: {e}。先頭の記事を採用します。")
        return list(range(min(top_n, len(articles))))


def research_article_with_search(
    client: genai.Client,
    model_name: str,
    article: NewsArticle,
    profile: CompanyProfile
) -> Optional[str]:
    """
    GeminiのGoogle Search Grounding（Web検索ツール）を活用し、
    記事の背景市場動向・類似競合事例・最新ファクトを追加調査する。
    """
    logger.info(f"Google検索グラウンディングによる追加リサーチ中: {article.title[:30]}...")

    prompt = f"""
あなたはビジネス戦略のシニアリサーチャーです。Google検索ツールを活用して以下の記事・トピックを深掘り調査してください。

【対象記事】
タイトル: {article.title}
出所: {article.source}
URL: {article.link}
概要/抜粋: {article.content[:600] if article.content else article.summary}

【調査観点】
1. この記事が取り上げている課題・ニーズの業界動向やマクロな背景（市場の深刻さや規模感）
2. 類似する先行事例や競合サービス、または使われている最新技術の実用例
3. スモールビジネスや「{profile.name}」のような事業者にとっての参入機会や留意点

客観的なファクトベースで、企画立案のインプットとなる要点を200〜300文字程度で簡潔に整理してください。
"""
    try:
        search_config = types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.3
        )
        response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=prompt,
            config=search_config
        )
        researched_text = response.text.strip() if response and response.text else None
        if researched_text:
            logger.info("Web検索グラウンディングによるリサーチが完了しました。")
        return researched_text
    except Exception as e:
        logger.warning(f"Web検索グラウンディング中にエラーが発生しました: {e}")
        return None


def generate_bizdev_analysis(
    api_key: str,
    model_name: str,
    articles: List[NewsArticle],
    profile: CompanyProfile,
    top_n: int = 5,
    research_config: dict = None
) -> WeeklyReport:
    """
    選定した複数の記事群をインプットとし、
    「複数の記事・動向を複合的に掛け合わせた（点と点を繋ぐ）新機軸アイデア」を立案・出力する
    """
    if research_config is None:
        research_config = {}

    enable_scraping = research_config.get("enable_scraping", True)
    max_article_chars = research_config.get("max_article_chars", 3500)
    enable_search_grounding = research_config.get("enable_search_grounding", True)

    client = genai.Client(api_key=api_key)

    # 複数記事の掛け合わせを行うため、最低でも4記事以上を分析対象とする
    articles_to_select = max(top_n, 4)
    logger.info(f"注目記事群の一次スクリーニング中 (選定目標: {articles_to_select}件)...")
    selected_indices = evaluate_and_filter_articles(
        client=client,
        model_name=model_name,
        articles=articles,
        profile=profile,
        top_n=articles_to_select
    )

    selected_articles = [articles[i] for i in selected_indices]
    logger.info(f"{len(selected_articles)} 件の記事を深掘り調査・統合分析対象として選定しました。")

    # Step A: 各選定記事の本文スクレイピング & 必要に応じてGoogle Search Grounding
    researched_articles_data = []
    for idx, art in enumerate(selected_articles, 1):
        logger.info(f"\n--- [記事 {idx}/{len(selected_articles)}] 本文取得 & 調査: {art.title[:30]} ---")
        
        # スクレイピング
        if enable_scraping and not art.content:
            art.content = fetch_article_content(art.link, max_chars=max_article_chars)

        # Web検索グラウンディング（重要上位記事）
        researched_facts = None
        if enable_search_grounding and idx <= 3:
            researched_facts = research_article_with_search(
                client=client,
                model_name=model_name,
                article=art,
                profile=profile
            )

        researched_articles_data.append({
            "article": art,
            "researched_facts": researched_facts
        })

    # Step B: 複数記事を掛け合わせた事業アイデアの統合生成
    logger.info("\n--- 複数記事のシナジー分析 & 事業創出アイデア（攻め×守り）の生成中 ---")

    # 記事群のテキストブロックを構築
    articles_block = ""
    for idx, item in enumerate(researched_articles_data, 1):
        art = item["article"]
        rf = item["researched_facts"]
        global_tag = "【🇺🇸 海外先行事例】" if art.is_global else "【🇯🇵 国内ニュース】"
        body_snippet = (art.content[:500] + "...") if art.content else (art.summary[:200] + "...")
        rf_text = f"\n  - 🔍 追加市場リサーチ: {rf}" if rf else ""
        
        articles_block += f"""
[記事{idx}] {global_tag}
・タイトル: {art.title}
・出所: {art.source}
・URL: {art.link}
・本文/概要抜粋: {body_snippet}{rf_text}
"""

    challenges_context = ""
    focus_kpi_text = ""
    if profile.current_challenges:
        focus_kpi_text = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])
        challenges_context = f"\n【自社の直近の注力課題 & 重点KPI】\n- 最重要KPI: {focus_kpi_text}\n"
        if issues:
            challenges_context += "- 解決したい切実な課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

    system_instruction = """
あなたは卓越したチーフビジネスストラテジストであり、同時に「冷徹な事業投資家・客観的戦略参謀（Devil's Advocate）」です。
あなたの最大の役割は、【複数のニュース記事や海外先行事例、最新技術トレンドを掛け合わせ（Cross-Pollination / 点と点を繋ぐ）】、
単一の記事だけでは見えてこない、自社独自の強力な新規事業・新機能アイデアを立案することです。

【重要指示：複数記事の掛け合わせ】
- 1つの記事だけを見てアイデアを作るのではなく、必ず【提示された記事群の中から2つ以上の異なる記事】を着想元として組み合わせてください。
  例: 「国内個人店の切実な人手不足・口コミ課題（記事A）」×「海外先行のマルチチャネル自動AIエージェント（記事B）」×「最新の生成AI広告/画像連携技術（記事C）」
- 各アイデアについて、なぜそれらの複数記事を組み合わせたのか（synergy_rationale）を明確に解説してください。
- 「攻め（マネタイズ、解決策、KPIインパクト）」だけでなく、「守り（実現性、最大の盲点・参入障壁、顧客受容性、参謀の辛口ジャッジ）」の両輪を容赦なく冷徹に評価してください。
"""

    prompt = f"""
以下の【選定された複数の注目記事一覧】および【自社プロファイル】をもとに、
記事同士のシナジー（点と点を繋ぐ掛け合わせ）から生まれる骨太な新規事業・マネタイズ企画を【2〜3件】立案し、
同時に客観的リスク・参入障壁を批判的に検証してください。

【収集・選定された注目記事一覧】
{articles_block}

【自社コンテキスト（自社の強みを活かす視点）】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}
{challenges_context}
【各アイデアの必須要件】
1. idea_title: 魅力的で具体的なアイデア企画名（例: 『〇〇×〇〇：店舗向け次世代AI〜』）
2. source_articles: 着想元となった【2つ以上の記事】のリスト（記事タイトル、URL、出所、要約、is_global）
3. synergy_rationale: なぜこの記事群を掛け合わせたのか、組み合わせることでどんな新しい価値や突破口が生まれるのか（150〜200文字程度）
4. market_pain: 複数記事から浮き彫りになる世の中の切実な課題・顧客のペイン
5. latest_tech: 活用されている、または組み合わせる最新技術・アプローチ
6. solution_idea: 「あなたならどう解決・事業化するか」具体的なサービス・ソリューション企画
7. monetization_model: 「どうやってお金を稼ぐか」マネタイズモデル（課金形態：月額SaaS、アップセル、代行手数料など）
8. kpi_impact: 自社の重点KPI（{focus_kpi_text or '顧客LTV・解約率・新規獲得'}）や課題に対してどう具体的に貢献するか
9. localization_opportunity: 海外事例を含む場合、日本国内の店舗・小規模事業者へのローカライズ機会や先行輸入・代行の可能性（国内記事のみの場合は null）
10. internal_next_action: 自社のアセットを活かして参入・PoCを進めるための最初のアクション仮説
11. feasibility_rating: 自社リソースでの実現性・難易度評価（「高」/「中」/「低」とその簡潔な理由）
12. critical_risks: 最大の盲点・参入障壁・大手競合の模倣リスク、やらない理由
13. customer_readiness: ターゲット顧客（個人店・小規模事業者など）の受容性・導入障壁
14. objective_verdict: 客観的参謀としての辛口ジャッジ（「即座に着手」「限定検証」「見送り」とその率直な根拠）

最後に overall_trend_comment に、今回分析した複数記事群から見える今週のAI・IT業界のマクロな潮目と総括コメント（200〜300文字）を記載してください。
"""

    try:
        response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=MultiArticleReportResponse,
                temperature=0.4
            )
        )
        res_data = json.loads(response.text)
        report_data = MultiArticleReportResponse(**res_data)
        ideas = report_data.ideas
        overall_comment = report_data.overall_trend_comment
        logger.info(f"複数記事を掛け合わせた事業アイデア {len(ideas)} 件の生成に成功しました！")
    except Exception as e:
        logger.error(f"統合アイデアの生成に失敗しました: {e}。フォールバック処理を実行します。")
        ideas = []
        overall_comment = "今週のIT・AI動向を踏まえ、新規ビジネス創出の種となる課題と技術をピックアップしました。"

    now_str = datetime.now().strftime("%Y年%m月%d日")
    focus_kpi = profile.current_challenges.get("focus_kpi") if profile.current_challenges else None

    report = WeeklyReport(
        report_title=f"【週次ビジネス成長レポート】最新AI・IT動向から紐解く新機軸アイデア ({now_str})",
        generated_at=now_str,
        company_name=profile.name,
        focus_kpi=focus_kpi,
        ideas=ideas,
        overall_trend_comment=overall_comment
    )

    return report


# エイリアス
generate_growth_analysis = generate_bizdev_analysis
