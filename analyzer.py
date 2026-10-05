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
        tags = []
        if getattr(art, "is_issue_driven", False):
            tags.append("【🎯自社課題逆引き】")
        if art.is_global:
            tags.append("[🇺🇸海外先行SaaS/動向]")
        else:
            tags.append("[🇯🇵国内ニュース]")
        prefix = "".join(tags) + " "
        context_str = f" (課題背景: {art.issue_context})" if getattr(art, "issue_context", None) else ""
        articles_text += f"[{idx}] {prefix}タイトル: {art.title} (出所: {art.source}){context_str}\n要約: {art.summary[:150]}\n\n"

    system_instruction = """
あなたはビジネス成長を牽引するチーフストラテジストです。
多数のニュース記事（自社課題逆引きリサーチ記事、国内ニュース、海外先行SaaS・プロダクト）の中から、
「世の中の切実な課題（ペイン）」や「最新技術の応用」「海外先行モデル」を含み、
【他の記事と掛け合わせることで強力な新規事業・自社課題解決の決定打になり得る記事】を厳選してください。
単なる単発リリースではなく、自社の課題突破口となる記事と、他動向を繋ぎ合わせてシナジーを生み出せる良質な記事群を優先してください。
"""

    challenges_text = ""
    if profile.current_challenges:
        kpi = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])
        challenges_text = f"\n【★最優先：自社が今直面している重点課題 & 注力KPI】\n- 重点KPI: {kpi}\n"
        if issues:
            challenges_text += "- 直近の課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

    prompt = f"""
以下の【自社プロファイル】と【ニュース記事一覧（自社課題逆引き＋国内＋海外先行事例）】を照合し、
自社の切実な課題を突破し、複数記事を掛け合わせて新機軸アイデアを創出するための注目記事を上位{top_n}件選定してください。

【自社プロファイル】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット顧客: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}
{challenges_text}
【選定基準】
1. 自社直近KPI・課題との合致度: 自社の重点KPIや切実な課題の突破口になり得るか（最優先。特に【🎯自社課題逆引き】タグの記事は必ず1件以上含めること）
2. シナジー性: 他の記事（自社課題解法 × 海外先行モデル × 最新AI技術など）と掛け合わせやすいか
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
    issue_contexts = set()
    for idx, item in enumerate(researched_articles_data, 1):
        art = item["article"]
        rf = item["researched_facts"]
        tags = []
        if getattr(art, "is_issue_driven", False):
            tags.append("【🎯 自社課題逆引きリサーチ】")
            if getattr(art, "issue_context", None):
                issue_contexts.add(art.issue_context)
        if art.is_global:
            tags.append("【🇺🇸 海外先行事例】")
        else:
            tags.append("【🇯🇵 国内ニュース】")
        global_tag = "".join(tags)
        body_snippet = (art.content[:500] + "...") if art.content else (art.summary[:200] + "...")
        rf_text = f"\n  - 🔍 追加市場リサーチ: {rf}" if rf else ""
        issue_ctx_text = f"\n  - 🎯 探求した自社課題: {art.issue_context}" if getattr(art, "issue_context", None) else ""
        
        articles_block += f"""
[記事{idx}] {global_tag}
・タイトル: {art.title}
・出所: {art.source}
・URL: {art.link}
・本文/概要抜粋: {body_snippet}{issue_ctx_text}{rf_text}
"""

    challenges_context = ""
    focus_kpi_text = ""
    if profile.current_challenges:
        focus_kpi_text = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])
        challenges_context = f"\n【自社の直近の注力課題 & 重点KPI】\n- 最重要KPI: {focus_kpi_text}\n"
        if issues:
            challenges_context += "- 解決したい切実な課題:\n" + "\n".join([f"  * {issue}" for issue in issues]) + "\n"

    resource_context = ""
    rc_hours = "週5〜10時間"
    rc_budget = "月1〜3万円"
    rc_skill = "ノーコード・AI活用"
    rc_team = "1〜2名"
    if profile.resource_constraints:
        rc = profile.resource_constraints
        rc_hours = rc.get("weekly_hours", rc_hours)
        rc_budget = rc.get("budget", rc_budget)
        rc_skill = rc.get("technical_skill", rc_skill)
        rc_team = rc.get("team_size", rc_team)
        resource_context = f"""
【自社の実行リソース制約（身の丈に合った提案のための最重要前提）】
- 週間投下工数: {rc_hours}
- 月間投下予算: {rc_budget}
- IT・技術スキル水準: {rc_skill}
- 実行体制（チーム規模）: {rc_team}
"""

    system_instruction = f"""
あなたは卓越したチーフビジネスストラテジストであり、同時に「冷徹な事業投資家・客観的戦略参謀（Devil's Advocate）」です。
あなたの最大の役割は、【自社が直面する切実な課題を突破する逆引き動向や海外先行事例、最新技術トレンドを掛け合わせ（Cross-Pollination / 点と点を繋ぐ）】、
クライアントがこれまで独力では思いつかなかった、自社独自の強力な課題解決策・新規事業アイデアを立案することです。

【重要指示1：自社課題突破と複数記事の掛け合わせ】
- 提案するアイデアのうち、最低1件は【自社が直面している切実な課題（addressed_issue）】を直接解決するための決定打・突破口アイデア（is_issue_driven_breakthrough = true）として設計してください。
- 1つの記事だけを見てアイデアを作るのではなく、必ず【提示された記事群の中から2つ以上の異なる記事（課題解法 × 海外モデル × 最新技術等）】を着想元として組み合わせてください。
- 各アイデアについて、なぜそれらの複数記事を組み合わせたのか（synergy_rationale）を明確に解説してください。
- 「攻め（マネタイズ、解決策、KPIインパクト）」だけでなく、「守り（実現性、最大の盲点・参入障壁、顧客受容性、参謀の辛口ジャッジ）」の両輪を容赦なく冷徹に評価してください。

【重要指示2：身の丈に合った提案粒度の調整（Resource-Fit / Feasible Sizing）】
- クライアントの【実行リソース制約（投下工数・予算・技術スキル・チーム規模）】を厳格に順守してください。
- 「非IT・スマホ中心」や「1人ワンオペ」「予算ゼロ〜小額」の場合：
  - 『独自のWeb診断ツールを開発する』『自前SaaSを構築する』『複雑なAPIパイプラインを組む』といった過大な提案は【絶対に禁止】です。
  - スマホ1台＋無料/低価格の既存ツール（LINE公式、Instagram、Canva、ChatGPT/Claude無料版、Googleフォーム等）のみを活用し、週末2〜3時間・追加予算0円から検証できる超身軽で即効性のある施策を立案してください。
- 逆に「エンジニア・自社開発可能」や予算・工数が十分にある場合は、API連携や独自データ蓄積、スクレイピング自動化など、技術的な差別化と参入障壁を築ける本格的なプロダクト・サービスを提案してください。
- 各アイデアについて、初期検証（PoC）に必要なリソース（required_resources）と、なぜ自社のリソース制約で無理なく実行できるのか（resource_fit_note）を必ず明記してください。
"""

    prompt = f"""
以下の【選定された複数の注目記事一覧（自社課題逆引きリサーチ＋国内外動向）】および【自社プロファイル】をもとに、
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
{challenges_context}{resource_context}
【各アイデアの必須要件】
1. idea_title: 魅力的で具体的なアイデア企画名（例: 『〇〇×〇〇：店舗向け次世代AI〜』）
2. addressed_issue: このアイデアがダイレクトに解決を狙う自社の切実な課題（直近の課題リストやKPIから該当するものを具体的に明記）
3. is_issue_driven_breakthrough: 自社課題の逆引きリサーチ記事を着想元とし、自社課題の決定打・突破口として設計されたアイデアかどうか（true / false。最低1件は true にすること）
4. source_articles: 着想元となった【2つ以上の記事】のリスト（記事タイトル、URL、出所、要約、is_global, is_issue_driven）
5. synergy_rationale: なぜこの記事群を掛け合わせたのか、組み合わせることでどんな新しい価値や突破口が生まれるのか（150〜200文字程度）
6. market_pain: 複数記事から浮き彫りになる世の中の切実な課題・顧客のペイン
7. latest_tech: 活用されている、または組み合わせる最新技術・アプローチ
8. solution_idea: 「あなたならどう解決・事業化するか」具体的なサービス・ソリューション企画（自社のITスキル・リソースで無理なく実行可能な現実的スコープにすること）
9. monetization_model: 「どうやってお金を稼ぐか」マネタイズモデル（課金形態：月額SaaS、アップセル、代行手数料、来店単価アップなど）
10. kpi_impact: 自社の重点KPI（{focus_kpi_text or '顧客LTV・解約率・新規獲得'}）や課題に対してどう具体的に貢献するか
11. localization_opportunity: 海外事例を含む場合、日本国内の店舗・小規模事業者へのローカライズ機会や先行輸入・代行の可能性（国内記事のみの場合は null）
12. internal_next_action: 自社のアセットを活かして参入・PoCを進めるための最初のアクション仮説
13. required_resources: 初期検証（PoC）に必要なリソース目安（所要時間・予算・推奨ツール例。例: 『所要時間: 週末2時間、予算: 0円、推奨ツール: LINE公式＋ChatGPT無料版』）
14. resource_fit_note: 自社のリソース制約（投下工数: {rc_hours}、予算: {rc_budget}、スキル: {rc_skill}）にどう適合しているか・無理なく実行できる理由（100〜150文字程度）
15. feasibility_rating: 自社リソースでの実現性・難易度評価（「高」/「中」/「低」とその簡潔な理由）
16. critical_risks: 最大の盲点・参入障壁・大手競合の模倣リスク、やらない理由
17. customer_readiness: ターゲット顧客（個人店・小規模事業者など）の受容性・導入障壁
18. objective_verdict: 客観的参謀としての辛口ジャッジ（「即座に着手」「限定検証」「見送り」とその率直な根拠）
19. impact_score: 自社KPIおよび事業インパクト度（1〜5の整数。5が最大）
20. feasibility_score: 実現容易性・開発難易度（1〜5の整数。5が最も容易/低難易度、1が高難易度）
21. speed_score: PoC開始・市場投入のスピード感（1〜5の整数。5が最も即効性あり）
22. target_market_size: 想定市場規模感（「特大」「大」「中」「ニッチ」のいずれか）
23. visual_diagram_mermaid: 利用者がこのアイデアの仕組みや顧客体験・業務フローを一目で直感的に理解できるよう、4〜6ノードで構成される簡潔なMermaid.jsダイアグラム構文（flowchart LR形式、バッククォートなし）。日本語ラベルには半角引用符["..."]を使用し、特殊記号は避けてください。
    例: flowchart LR\n  A["👤 顧客"] -->|"来店・相談"| B["📱 店舗LINE/Web"]\n  B -->|"データ連携"| C["🤖 AIエンジン"]\n  C -->|"個別最適化提案"| D["🎯 自社スタッフ"]\n  D -->|"LTV向上"| E["📈 KPI達成"]

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

    # 課題逆引きリサーチのサマリー構築
    issue_summary = None
    if issue_contexts:
        issue_summary = "、".join(list(issue_contexts)[:2])
    elif profile.current_challenges and profile.current_challenges.get("urgent_issues"):
        issue_summary = profile.current_challenges["urgent_issues"][0]

    report = WeeklyReport(
        report_title=f"【週次ビジネス成長レポート】最新AI・IT動向から紐解く新機軸アイデア ({now_str})",
        generated_at=now_str,
        company_name=profile.name,
        focus_kpi=focus_kpi,
        issue_research_summary=issue_summary,
        ideas=ideas,
        overall_trend_comment=overall_comment
    )

    return report


# エイリアス
generate_growth_analysis = generate_bizdev_analysis


def consult_idea_with_advisor(
    api_key: str,
    model_name: str,
    idea: dict,
    profile: dict,
    question: str,
    chat_history: list = None
) -> str:
    """
    対象の事業アイデアと自社プロファイルをコンテキストとし、
    経営者・事業担当者からの疑問や壁打ち（営業トーク、PoC手順、価格設定、リスク回避など）に
    チーフストラテジストとして具体的・実践的に回答する。
    """
    client = genai.Client(api_key=api_key)

    company_name = profile.get("name", "自社")
    kpi = profile.get("current_challenges", {}).get("focus_kpi", "")
    issues = profile.get("current_challenges", {}).get("urgent_issues", [])
    issues_text = "\n".join([f"- {iss}" for iss in issues]) if issues else "なし"

    rc = profile.get("resource_constraints", {}) or {}
    rc_hours = rc.get("weekly_hours", "週5〜10時間")
    rc_budget = rc.get("budget", "月1〜3万円")
    rc_skill = rc.get("technical_skill", "ノーコード・AI活用")
    rc_team = rc.get("team_size", "1〜2名")
    resource_info = f"投下可能時間: {rc_hours} / 予算: {rc_budget} / ITスキル: {rc_skill} / 体制: {rc_team}"

    system_instruction = f"""
あなたは卓越したチーフビジネスストラテジストであり、「{company_name}」の専属戦略参謀（Devil's Advocate兼実践的アドバイザー）です。
提示された事業アイデアと自社の置かれた状況を踏まえ、事業責任者・経営者からの壁打ち相談に対して、以下の原則で回答してください：

【回答原則】
1. 抽象論を徹底排除し、明日から現場で使える【超具体的・実践的なアクション】を提示する。
   - 営業トークの相談なら、そのまま口に出せる「最初の1分フックトーク」「反論切り返しトーク」をセリフ形式（『〜』）で具体的に作成する。
   - PoC検証なら、「Day 1〜2」「Day 3〜5」といった1週間の実働スケジュールや推奨ツール・プロンプト例まで踏み込む。
   - 価格設定なら、月額・初期費用・アップセルの具体的な金額案と提供価値ロジックを提示する。
   - リスク回避なら、想定されるトラブルと事前の契約・運用ルールを明示する。
2. クライアントの【実行リソース制約（{resource_info}）】を常に大前提とし、身の丈に合わない過大な開発や高額ツールの導入は避け、現状のリソースで無理なく完結する現実的なアプローチを授ける。
3. 自社の強み・保有アセットをどうテコにするかを常に意識する。
4. 迎合せず、客観的・冷徹なプロの参謀視点を保つ。
5. Markdown形式で見やすく構造化（見出し、箇条書き、太字など）して回答する。
"""

    idea_context = f"""
【検討対象の事業アイデア】
・アイデア名: {idea.get('idea_title') or idea.get('article_title', '名称未定')}
・解決する課題 (Pain): {idea.get('market_pain', '')}
・活用技術 (Tech): {idea.get('latest_tech', '')}
・解決・事業化案: {idea.get('solution_idea', '')}
・マネタイズモデル: {idea.get('monetization_model', '')}
・自社KPIへの貢献: {idea.get('kpi_impact', '')}
・自社での最初の打ち手: {idea.get('internal_next_action', '')}
・推奨PoCリソース: {idea.get('required_resources', '未指定')}
・リソース適合理由: {idea.get('resource_fit_note', '未指定')}
・実現性・難易度: {idea.get('feasibility_rating', '')}
・最大の盲点・リスク: {idea.get('critical_risks', '')}
・顧客受容性: {idea.get('customer_readiness', '')}
・参謀の辛口ジャッジ: {idea.get('objective_verdict', '')}

【自社コンテキスト】
・会社・事業名: {company_name}
・主要事業: {profile.get('core_business', '')}
・ターゲット: {profile.get('target_customers', '')}
・自社の強み・アセット: {', '.join(profile.get('key_assets', [])) if isinstance(profile.get('key_assets'), list) else profile.get('key_assets', '')}
・重点KPI: {kpi}
・直近の切実な課題:
{issues_text}
・実行リソース制約: {resource_info}
"""

    # 対話履歴のフォーマット
    conversation_text = ""
    if chat_history and isinstance(chat_history, list):
        for turn in chat_history[-6:]:  # 直近最大6往復
            role_name = "相談者（経営者/事業開発）" if turn.get("role") == "user" else "戦略参謀（あなた）"
            conversation_text += f"\n[{role_name}]: {turn.get('text', '')}\n"

    prompt = f"""
{idea_context}

これまでの壁打ち履歴:
{conversation_text if conversation_text else "（これが最初の相談です）"}

[相談者の最新の質問・相談内容]:
{question}

上記に対して、専属戦略参謀として、明日から即座に現場で使える超具体的かつ実践的なアドバイス・打ち手を回答してください。
"""

    try:
        response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"壁打ちAIの応答生成中にエラーが発生しました: {e}")
        return f"申し訳ありません。戦略参謀AIとの対話生成中にエラーが発生しました: {str(e)}"

