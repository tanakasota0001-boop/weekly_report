import json
import logging
from typing import List
from datetime import datetime
from google import genai
from google.genai import types

from models import (
    CompanyProfile,
    NewsArticle,
    BizDevIdea,
    WeeklyReport
)
from gemini_helper import generate_with_fallback
from scraper import fetch_article_content

logger = logging.getLogger(__name__)


def evaluate_and_filter_articles(
    client: genai.Client,
    model_name: str,
    articles: List[NewsArticle],
    profile: CompanyProfile,
    top_n: int = 3
) -> List[int]:
    """
    収集したニュース記事一覧を自社プロファイルと照らし合わせ、
    ビジネス成長の観点から最も着目すべき上位top_n件のインデックスを返す
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
多数のニュース記事（国内ニュースおよび海外先行SaaS・プロダクト）の中から、「世の中の切実な課題（ペイン）」を含み、「最新技術を絡めたビジネス創出の種」になり得る記事を厳選してください。
海外の先行事例については、「日本の小規模事業者向けにタイムマシン的に輸入・ローカライズできるか」という視点も高く評価してください。
単なる企業の広報リリースや一般ニュースは除外し、自社のビジネス成長にとって実利のある記事を優先してください。
"""

    challenges_text = ""
    if profile.current_challenges:
        kpi = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])
        challenges_text = f"\n【★最優先：自社が今直面している重点課題 & 注力KPI】\n- 重点KPI: {kpi}\n"
        if issues:
            challenges_text += "- 直近の課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

    prompt = f"""
以下の【自社プロファイル】と【ニュース記事一覧（国内＋海外先行事例）】を照合し、ビジネス成長・新機軸創出の観点から最も注目・深掘りすべき記事を上位{top_n}件選定してください。

【自社プロファイル】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット顧客: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}
{challenges_text}
【選定・スコアリング基準】
1. 自社直近KPIとの合致度: 自社の重点KPIや直近の切実な課題の解決・突破口になり得るか（最優先）
2. 課題の深刻度: 世の中や顧客の強いペイン・不満が潜んでいるか
3. 新規性・技術性: AIやITの最新動向を活かせる余地があるか
4. 自社親和性 & タイムマシン価値: 自社のアセットを活用できるか、または海外モデルを日本市場へ先回り応用できるか

【ニュース記事一覧】
{articles_text}

出力は以下のJSON形式で、上位{top_n}件のインデックス番号の配列のみを出力してください:
{{
  "selected_indices": [0, 2, 5]
}}
"""

    from gemini_helper import generate_with_fallback

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
        # インデックスのバリデーション
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
        # Google Search Tool を設定
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
        logger.warning(f"Web検索グラウンディング中にエラーが発生しました（スクレイピング結果のみで継続します）: {e}")
        return None


def generate_bizdev_analysis(
    api_key: str,
    model_name: str,
    articles: List[NewsArticle],
    profile: CompanyProfile,
    top_n: int = 3,
    research_config: dict = None
) -> WeeklyReport:
    """
    選定した記事を深掘り分析し、ビジネス創出（マネタイズ）視点の週次レポートを生成する
    """
    if research_config is None:
        research_config = {}

    enable_scraping = research_config.get("enable_scraping", True)
    max_article_chars = research_config.get("max_article_chars", 3500)
    enable_search_grounding = research_config.get("enable_search_grounding", True)

    client = genai.Client(api_key=api_key)

    logger.info("記事の一次スクリーニング中...")
    selected_indices = evaluate_and_filter_articles(
        client=client,
        model_name=model_name,
        articles=articles,
        profile=profile,
        top_n=top_n
    )

    selected_articles = [articles[i] for i in selected_indices]
    logger.info(f"{len(selected_articles)} 件の記事を深掘り分析対象として選定しました。")

    ideas: List[BizDevIdea] = []

    system_instruction = """
あなたは卓越したビジネス成長ストラテジストであり、同時に「冷徹な事業投資家・客観的戦略参謀（Devil's Advocate）」です。
提供された記事の一次情報（本文テキストやWeb検索リサーチ結果）から、新規ビジネスのチャンス（攻め）を見出すだけでなく、そのアイデアに潜む致命的なリスクや参入障壁、顧客が動かない理由（守り・客観的批判）を容赦なく検証してください。

単なる「面白そうなアイデア」を称賛するイエスマンではなく、
・【攻め】誰が切実にお金を払うのか、どうマネタイズし、自社アセットで優位性を作るか
・【守り】大手が真似したらどう防ぐか、なぜ失敗しやすいか、ターゲット（ITが苦手な小規模店など）が導入をためらう要因は何か
・【客観判定】自社リソースで本当に即座に着手できるか、今やるべきか見送るべきか
の双方を冷徹に分析し、実効性の高いアドバイスを提示してください。
"""

    for art in selected_articles:
        logger.info(f"\n--- 記事分析開始: {art.title[:30]} ---")

        # Step A-1: 本文スクレイピング
        if enable_scraping:
            art.content = fetch_article_content(art.link, max_chars=max_article_chars)

        # Step A-2: Web検索グラウンディングによる追加リサーチ
        researched_facts = None
        if enable_search_grounding:
            researched_facts = research_article_with_search(
                client=client,
                model_name=model_name,
                article=art,
                profile=profile
            )

        # Step B: 構造化事業アイデア生成
        logger.info(f"アイデア生成中: {art.title[:30]}...")

        # プロンプト用の本文・リサーチ情報ブロック
        if art.content:
            article_body_text = f"【記事本文テキスト（スクレイピング結果）】\n{art.content}\n"
        else:
            article_body_text = f"【記事概要（RSSスニペット）】\n{art.summary}\n"

        research_text = (
            f"【最新Web検索・市場リサーチ情報（Google Search Grounding）】\n{researched_facts}\n"
            if researched_facts else ""
        )

        challenges_context = ""
        focus_kpi_text = ""
        if profile.current_challenges:
            focus_kpi_text = profile.current_challenges.get("focus_kpi", "")
            issues = profile.current_challenges.get("urgent_issues", [])
            challenges_context = f"\n【自社の直近の注力課題 & 重点KPI】\n- 最重要KPI: {focus_kpi_text}\n"
            if issues:
                challenges_context += "- 解決したい切実な課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

        global_context = ""
        if art.is_global:
            global_context = (
                "【★海外先行事例（Product Hunt / 米国Tech動向）としての分析指示】\n"
                "- 本記事は英語・海外の最新先行プロダクト/動向です。\n"
                "- source_summary は英語の事実をわかりやすい日本語で要約してください。\n"
                "- タイムマシン経営の視点から、この海外モデルを「ITが苦手な日本の個人店・小規模事業者向けにどうローカライズ・代行導入して先回りするか」を localization_opportunity に具体的に記述してください。\n\n"
            )

        prompt = f"""
以下の記事情報および市場リサーチ結果をもとに、新規ビジネス創出・マネタイズ企画を立案し、同時に客観的リスク・参入障壁を批判的に検証してください。

【対象記事】
タイトル: {art.title}
出所: {art.source} {'(🇺🇸海外先行事例)' if art.is_global else '(🇯🇵国内ニュース)'}
URL: {art.link}
{article_body_text}
{research_text}
{global_context}【自社コンテキスト（自社の強みを活かす視点）】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}
{challenges_context}
以下の項目を検討し、JSONで出力してください:
1. source_summary: 記事が伝えている客観的事実・要約（海外記事の場合は日本語で平易に150文字程度）
2. researched_facts: Web検索や記事詳細から判明した市場背景やファクト・競合動向（150〜200文字程度）
3. market_pain: 今世の中で浮き彫りになっている未解決の課題・顧客のペイン（誰が何に困っているか）
4. latest_tech: 活用されている、または活用できる最新技術・アプローチ

【攻めの事業企画】
5. solution_idea: 「あなたならどう解決・事業化するか」具体的なサービス・ソリューション企画（具体的に誰に何を提供するか）
6. monetization_model: 「どうやってお金を稼ぐか」マネタイズモデル（課金形態：月額SaaS、成果報酬、導入支援＋保守、手数料率など具体的に）
7. kpi_impact: 自社の重点KPI（{focus_kpi_text or '顧客LTV・解約率・売上'}）や直近課題に対して、このアイデアがどう具体的に寄与・貢献するか（定量的または定性的なインパクト）
8. localization_opportunity: （海外事例の場合は必須）日本国内の店舗・小規模事業者へのローカライズ機会や先行輸入・代行の可能性、参入障壁への対策（国内記事の場合は null）
9. internal_next_action: 自社のアセットを活用して参入・PoCを進めるための検証論点・最初のアクション仮説

【守り・リスク評価（客観的批判・参謀視点）】
10. feasibility_rating: 自社リソースでの実現性・難易度評価（「高 (既存技術で1〜2ヶ月でPoC可能)」 / 「中 (一部外部連携や開発が必要)」 / 「低 (大規模開発や専門リソースが必要)」とその簡潔な理由）
11. critical_risks: 最大の盲点・参入障壁・大手競合（BASE, ペライチ, Shopify, リクルート等）の模倣リスク、やらない理由
12. customer_readiness: ターゲット顧客（個人店・小規模事業者など）の受容性・導入障壁（忙しさ、ITリテラシー、費用対効果への疑念など）
13. objective_verdict: 客観的参謀としての辛口ジャッジ（「今すぐ着手すべき」「条件付きで限定検証」「現時点では見送るべき」とその率直な根拠）
"""

        try:
            response = generate_with_fallback(
                client=client,
                preferred_model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=BizDevIdea,
                    temperature=0.4
                )
            )
            idea_data = json.loads(response.text)
            
            # researched_factsが空で、事前リサーチが存在する場合は補完
            if not idea_data.get("researched_facts") and researched_facts:
                idea_data["researched_facts"] = researched_facts

            idea = BizDevIdea(
                article_title=art.title,
                article_url=art.link,
                is_global=art.is_global,
                **{k: v for k, v in idea_data.items() if k not in ["article_title", "article_url", "is_global"]}
            )
            ideas.append(idea)
        except Exception as e:
            logger.error(f"アイデアの生成に失敗しました ({art.title}): {e}")

    # 全体総括の生成
    overall_prompt = f"""
今回分析した以下の{len(ideas)}件のアイデアから、今週のAI・IT業界におけるマクロな潮目・トレンドと、
今後のビジネス展開において意識すべき総括コメント（200〜300文字程度）を作成してください。

取り上げた記事:
{chr(10).join(['- ' + i.article_title for i in ideas])}
"""
    try:
        trend_response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=overall_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3
            )
        )
        overall_comment = trend_response.text.strip()
    except Exception as e:
        logger.warning(f"総括コメントの生成に失敗しました: {e}")
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


# エイリアス（自然な呼称として提供）
generate_growth_analysis = generate_bizdev_analysis
