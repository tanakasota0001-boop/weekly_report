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
    事業開発視点で最も着目すべき上位top_n件のインデックスを返す
    """
    if not articles:
        return []

    # 記事リストをテキスト化
    articles_text = ""
    for idx, art in enumerate(articles):
        articles_text += f"[{idx}] タイトル: {art.title} (出所: {art.source})\n要約: {art.summary[:150]}\n\n"

    system_instruction = """
あなたは事業開発部専属のチーフストラテジストです。
多数のニュース記事の中から、「世の中の切実な課題（ペイン）」を含み、「最新技術を絡めたビジネス創出の種」になり得る記事を厳選してください。
単なる企業の広報リリースや一般ニュースは除外し、自社の事業開発にとって実利のある記事を優先してください。
"""

    prompt = f"""
以下の【自社プロファイル】と【ニュース記事一覧】を照合し、事業開発の観点から最も注目・深掘りすべき記事を上位{top_n}件選定してください。

【自社プロファイル】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット顧客: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}

【選定・スコアリング基準】
1. 課題の深刻度: 世の中や顧客の強いペイン・不満が潜んでいるか
2. 新規性・技術性: AIやITの最新動向を活かせる余地があるか
3. 自社親和性: 自社のアセット（顧客基盤や技術）を活用して参入・マネタイズできる余地があるか

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


def generate_bizdev_analysis(
    api_key: str,
    model_name: str,
    articles: List[NewsArticle],
    profile: CompanyProfile,
    top_n: int = 3
) -> WeeklyReport:
    """
    選定した記事を深掘り分析し、ビジネス創出（マネタイズ）視点の週次レポートを生成する
    """
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
あなたは卓越した事業開発（BizDev）アントレプレナーであり、AI/ITビジネスのプロです。
最新のニュース記事から「課題（Pain）」「技術（Tech）」を抽出し、「あなたならどうビジネスを作り、お金を稼ぐか」を具体的かつ現実的に企画立案してください。

単なる「マッチングアプリを作る」「一般的な相談SaaS」などの机上の空論・抽象論は避け、
・誰が切実にお金を払うのか（顧客と提供価値）
・どうやって初期顧客を獲得し、継続課金（マネタイズ）させるか
・自社の強み・アセットをどうテコにして参入障壁を築くか
をシャープに論じてください。
"""

    for art in selected_articles:
        logger.info(f"事業アイデア生成中: {art.title[:30]}...")
        prompt = f"""
以下の記事をもとに、新規事業開発・マネタイズ企画を立案してください。

【対象記事】
タイトル: {art.title}
出所: {art.source}
URL: {art.link}
概要: {art.summary}

【自社コンテキスト（自社の強みを活かす視点）】
- 会社・部門: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}
- 注力テーマ: {', '.join(profile.focus_themes)}

以下の項目を検討し、JSONで出力してください:
1. source_summary: 記事が伝えている客観的事実・要約（150文字程度）
2. market_pain: 今世の中で浮き彫りになっている未解決の課題・顧客のペイン（誰が何に困っているか）
3. latest_tech: 活用されている、または活用できる最新技術・アプローチ
4. solution_idea: 「あなたならどう解決・事業化するか」具体的なサービス・ソリューション企画（具体的に誰に何を提供するか）
5. monetization_model: 「どうやってお金を稼ぐか」マネタイズモデル（課金形態：月額SaaS、成果報酬、導入支援＋保守、手数料率など具体的に）
6. internal_next_action: 自社のアセットを活用して参入・PoCを進めるための検証論点・最初のアクション仮説
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
            idea = BizDevIdea(
                article_title=art.title,
                article_url=art.link,
                **{k: v for k, v in idea_data.items() if k not in ["article_title", "article_url"]}
            )
            ideas.append(idea)
        except Exception as e:
            logger.error(f"事業アイデアの生成に失敗しました ({art.title}): {e}")

    # 全体総括の生成
    overall_prompt = f"""
今回分析した以下の{len(ideas)}件の事業アイデアから、今週のAI・IT業界におけるマクロな潮目・トレンドと、
事業開発部として意識すべき総括コメント（200〜300文字程度）を作成してください。

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
        overall_comment = "今週のIT・AI動向を踏まえ、新規事業の種となる課題と技術をピックアップしました。"

    now_str = datetime.now().strftime("%Y年%m月%d日")
    report = WeeklyReport(
        report_title=f"【週次BizDevレポート】最新AI・IT動向から紐解く新規事業アイデア ({now_str})",
        generated_at=now_str,
        company_name=profile.name,
        ideas=ideas,
        overall_trend_comment=overall_comment
    )

    return report
