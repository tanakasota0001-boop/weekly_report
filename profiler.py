import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from models import CompanyProfile, CompanyProfileBase

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"
DEFAULT_CACHE_FILE = os.path.join(CACHE_DIR, "company_profile.json")


def get_cache_file_path(profile_id: Optional[str] = None, name: str = "") -> str:
    """プロファイルIDまたは会社名に応じたキャッシュファイルパスを返す"""
    if profile_id:
        import re
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", profile_id.lower()).strip("_")
        return os.path.join(CACHE_DIR, f"company_profile_{clean_id}.json")
    return DEFAULT_CACHE_FILE


def fetch_website_text(url: str, max_chars: int = 4000) -> str:
    """指定されたURLからWebページの主要テキストを抽出する"""
    if not url or url.strip() == "" or "example.com" in url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        logger.info(f"自社URLをスクレイピング中: {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=10, verify=True)
        except requests.exceptions.SSLError as se:
            logger.warning(f"自社URLのSSL証明書検証に失敗しました ({url}): {se}。安全なフォールバック (verify=False) で再試行します。")
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=headers, timeout=10, verify=False)

        resp.encoding = resp.apparent_encoding
        if resp.status_code != 200:
            logger.warning(f"URLへのアクセスに失敗しました (Status: {resp.status_code}): {url}")
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        text = " ".join(soup.stripped_strings)
        return text[:max_chars]
    except Exception as e:
        logger.warning(f"Webサイトの取得に失敗しました ({url}): {e}")
        return ""


def build_company_profile(
    api_key: str,
    model_name: str,
    name: str,
    url: str,
    notes: str,
    force_refresh: bool = False,
    current_challenges: Optional[dict] = None,
    profile_id: Optional[str] = None,
    resource_constraints: Optional[dict] = None
) -> CompanyProfile:
    """自社URLと補足情報から、ビジネス成長・新機軸創出のための企業プロファイルを生成・キャッシュする"""
    os.makedirs(CACHE_DIR, exist_ok=True)

    cache_file = get_cache_file_path(profile_id, name)
    # 既存のレガシーキャッシュ (company_profile.json) からのフォールバック
    if not os.path.exists(cache_file) and (profile_id == "haveasite" or "haveasite" in name.lower()):
        if os.path.exists(DEFAULT_CACHE_FILE):
            cache_file = DEFAULT_CACHE_FILE

    # キャッシュが存在し、再生成フラグが立っていない場合はキャッシュを返す
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"キャッシュされた自社プロファイルを読み込みました ({cache_file})。")
                profile = CompanyProfile(**data)
                # 直近の課題・KPIおよびリソース制約は動的に最新のものを注入
                profile.current_challenges = current_challenges
                profile.resource_constraints = resource_constraints
                return profile
        except Exception as e:
            logger.warning(f"キャッシュの読み込みに失敗したため、再生成します: {e}")

    # Webサイトテキストの取得
    site_text = fetch_website_text(url)

    # Geminiクライアントの初期化
    client = genai.Client(api_key=api_key)

    system_instruction = """
あなたはトップクラスのビジネス成長ストラテジスト・客観的戦略参謀です。
入力された企業のWebサイト情報や補足指示を分析し、ビジネス成長・新機軸創出のベースとなる「自社プロファイル」を構造化して出力してください。
"""

    prompt = f"""
以下の企業情報をもとに、ビジネス成長・新機軸創出を行うための自社プロファイルを整理してください。

【会社・事業部名】
{name}

【補足メモ・注力テーマ】
{notes}

【自社Webサイトからの抽出テキスト】
{site_text if site_text else "（Webサイト情報の取得なし。補足メモに基づいて分析してください）"}

以下のJSON形式で出力してください:
{{
  "name": "{name}",
  "core_business": "主要事業とコアバリュー（1〜2文）",
  "target_customers": "ターゲットとする顧客属性や業界",
  "key_assets": ["保有する強み・アセット1", "強み2", "強み3"],
  "focus_themes": ["注力・関心のあるテーマ1", "テーマ2"],
  "raw_summary": "自社が新規事業を検討する上での前提となる立ち位置の総括サマリー（200文字程度）"
}}
"""

    from gemini_helper import generate_with_fallback

    logger.info("Geminiによる自社プロファイルの分析中...")
    response = generate_with_fallback(
        client=client,
        preferred_model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=CompanyProfileBase,
            temperature=0.2
        )
    )

    profile_data = json.loads(response.text)
    profile = CompanyProfile(**profile_data)
    profile.current_challenges = current_challenges
    profile.resource_constraints = resource_constraints

    # キャッシュに保存
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)
    logger.info(f"自社プロファイルをキャッシュに保存しました: {cache_file}")

    return profile


class WizardQuestion(BaseModel):
    """問診の各質問"""
    id: str = Field(description="質問ID (例: q_channel, q_strength, q_pain, q_resource)")
    title: str = Field(description="質問の短いテーマ (例: 集客の現状、実行リソース等)")
    question: str = Field(description="経営者・オーナーに問いかける質問文")
    options: List[str] = Field(description="選択しやすい3〜4個の具体的な回答候補")
    placeholder: str = Field(default="", description="自由記述欄のプレースホルダー")


class WizardQuestionsResponse(BaseModel):
    """AIが生成した戦略問診票"""
    business_summary: str = Field(description="入力から推測されるビジネスの現状サマリー（1〜2文）")
    detected_industry: str = Field(description="推定される業界・業態カテゴリ")
    questions: List[WizardQuestion] = Field(description="状況を診断するための4つの質問")


def generate_wizard_questions(
    api_key: str,
    model_name: str,
    name: str,
    url: str = "",
    notes: str = ""
) -> dict:
    """
    簡単な会社名・URL・一言メモから、戦略参謀AIがそのビジネスに合わせた4つの核心的な問診票を生成する
    """
    client = genai.Client(api_key=api_key)
    site_text = fetch_website_text(url) if url else ""

    from gemini_helper import generate_with_fallback

    system_instruction = """
あなたは腕利きのビジネス戦略コンサルタント・戦略参謀です。
新規クライアント（ビジネスオーナーや起業検討中の個人）の初回ヒアリングにおいて、
事業の強み、ターゲット、最重要KPI、切実な課題、そして【実行リソース制約（時間・予算・ITスキル）】を
短時間で的確に引き出すための【4つの動的問診質問】を作成してください。

【問診の4大テーマ】
1. 現在の顧客獲得・集客手段（どこから来ていて何が課題か）
2. 顧客から選ばれている強み・競合との違い（価格、技術、立地、サービス、アセット）
3. 今月・今年一番頭を抱えているボトルネック・解決したい切実な課題
4. 実行リソース・スキル状況（投下可能時間、月間予算、ITスキルレベル。身の丈に合った提案をするための必須項目）

オーナーが選択しやすいよう、業種や入力内容に即した具体的でリアルな選択肢（各3〜4個）を用意してください。
"""

    prompt = f"""
以下のビジネス情報をもとに、戦略プロファイルを作成するための4つの問診質問を作成してください。

【会社・事業名】
{name}

【URL】
{url or 'なし'}

【事業メモ・一言概要】
{notes or '（未記入）'}

【Webサイトからの抽出テキスト】
{site_text[:1500] if site_text else 'なし'}
"""

    try:
        response = generate_with_fallback(
            client=client,
            preferred_model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=WizardQuestionsResponse,
                temperature=0.3
            )
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"問診質問生成エラー: {e}")
        # フォールバック汎用質問
        return {
            "business_summary": f"{name}のビジネス状況の診断",
            "detected_industry": "スモールビジネス",
            "questions": [
                {
                    "id": "q_channel",
                    "title": "現在の集客・顧客獲得状況",
                    "question": "現在、新規顧客は主にどのような経路から来ていますか？",
                    "options": [
                        "Instagram等のSNSやWeb広告が中心だが、費用や手間の割にリピートが弱い",
                        "紹介や口コミ、飛び込み営業が中心で、スケールや安定獲得が難しい",
                        "ポータルサイトやプラットフォームに依存しており、手数料が高い"
                    ],
                    "placeholder": "その他の経路や現状があればご記入ください"
                },
                {
                    "id": "q_strength",
                    "title": "独自の強み・選ばれる理由",
                    "question": "顧客から評価されている自社ならではの強みやアセットは何ですか？",
                    "options": [
                        "他社にはない高い技術力や品質・専門性",
                        "圧倒的なスピードやフットワークの軽さ・柔軟性",
                        "顧客との深い信頼関係や丁寧なマンツーマン対応",
                        "低コスト・明確で試しやすい料金体系"
                    ],
                    "placeholder": "自社ならではの強みをご記入ください"
                },
                {
                    "id": "q_pain",
                    "title": "直近の最も切実な課題",
                    "question": "今直面している、最も頭を抱えているボトルネックは何ですか？",
                    "options": [
                        "集客数が足りず、新規リードの獲得が最優先",
                        "顧客は来るが単価が低く、利益率やLTVを高めたい",
                        "人手・リソース不足で、日々の運用や提案に追われている",
                        "大手の競合や同質化に埋もれて差別化ができていない"
                    ],
                    "placeholder": "最も解決したい課題をご記入ください"
                },
                {
                    "id": "q_resource",
                    "title": "実行リソース（時間・予算・ITスキル）",
                    "question": "新しい施策やAI活用を試す場合、どの程度のリソース（時間・費用・スキル）を投下できますか？",
                    "options": [
                        "非IT・スマホ中心、使える時間は週末2〜3時間、予算は0円（無料ツールのみ）で始めたい",
                        "日常業務の合間に週5〜10時間、月1〜3万円のツール代ならOK、ノーコードやAIツールは使える",
                        "専任または副業で週15時間以上、月3〜5万円以上OK、エンジニアリングや自社開発も可能"
                    ],
                    "placeholder": "投下できるリソース状況をご記入ください"
                }
            ]
        }


def synthesize_wizard_profile(
    api_key: str,
    model_name: str,
    name: str,
    url: str = "",
    notes: str = "",
    qa_list: list = None
) -> dict:
    """
    問診での回答をもとに、高精度な戦略プロファイル（強み、KPI、課題、キーワード）を合成生成する
    """
    client = genai.Client(api_key=api_key)
    from gemini_helper import generate_with_fallback

    qa_text = ""
    if qa_list and isinstance(qa_list, list):
        for qa in qa_list:
            q = qa.get("question", "")
            a = qa.get("answer", "")
            qa_text += f"\n- 質問: {q}\n  回答: {a}\n"

    system_instruction = """
あなたはチーフビジネスストラテジストです。
クライアントからの問診回答をもとに、新規事業・AI活用・成長戦略を立案するための【洗練された戦略プロファイル】を構造化して出力してください。

【生成要件】
1. name: 会社・サービス名
2. url: 公式URL
3. notes: サービス概要、ターゲット、独自の強み、今後の注力テーマを整理したプロフェッショナルなサマリーメモ（マークダウン箇条書き含む）
4. current_challenges:
   - focus_kpi: 明確で行動に直結する「最優先の重点KPI」（例: 「平日アイドルタイムの客単価20%向上とリピート率改善」「新規リード月間15件獲得」などシャープに）
   - urgent_issues: 解決したい切実な課題のリスト（2〜3項目。現場のリアリティのある表現で）
5. resource_constraints: 実行リソース制約
   - weekly_hours: 新規施策に投下できる週間工数（例: 「週2〜3時間」「週5〜10時間」「週15時間以上」）
   - budget: 新規施策に使える月間予算（例: 「完全ゼロ（無料ツールのみ）」「月1〜3万円」「月5万円以上」）
   - technical_skill: IT・技術スキル（例: 「非IT・スマホ中心」「ノーコード・AI活用」「エンジニア・自社開発」）
   - team_size: チーム規模（例: 「1人（ワンオペ）」「2〜3名」「5名以上」）
6. keywords: このビジネスの課題解決やAI活用に最適なニュース検索キーワードのリスト（4〜5項目）
"""

    prompt = f"""
以下の問診回答と基本情報をもとに、戦略プロファイルを作成してください。

【会社・事業名】
{name}

【URL】
{url or 'なし'}

【事前メモ】
{notes or 'なし'}

【戦略問診のQ&A回答結果】
{qa_text}

以下のJSON形式で出力してください:
{{
  "name": "{name}",
  "url": "{url}",
  "notes": "【サービス概要】...\\n\\n【ターゲット顧客】...\\n\\n【保有アセット・強み】...\\n\\n【今後の注力テーマ】...",
  "current_challenges": {{
    "focus_kpi": "最重要KPI（1文）",
    "urgent_issues": [
      "切実な課題1",
      "切実な課題2"
    ]
  }},
  "resource_constraints": {{
    "weekly_hours": "週5〜10時間",
    "budget": "月1〜3万円",
    "technical_skill": "ノーコード・AI活用",
    "team_size": "1〜2名"
  }},
  "keywords": [
    "キーワード1",
    "キーワード2",
    "キーワード3",
    "キーワード4"
  ]
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
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"戦略プロファイル合成エラー: {e}")
        # フォールバック
        return {
            "name": name,
            "url": url,
            "notes": f"【事業概要】\n{notes}\n\n【問診回答】\n{qa_text}",
            "current_challenges": {
                "focus_kpi": "新規顧客の獲得と売上向上",
                "urgent_issues": ["集客とリピートの安定化", "リソース・時間の不足"]
            },
            "resource_constraints": {
                "weekly_hours": "週2〜3時間",
                "budget": "完全ゼロ（無料ツールのみ）",
                "technical_skill": "非IT・スマホ中心",
                "team_size": "1人（ワンオペ）"
            },
            "keywords": [f"{name} ビジネス", "店舗 DX AI", "スモールビジネス 集客 自動化"]
        }

