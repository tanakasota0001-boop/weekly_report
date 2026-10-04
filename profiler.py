import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional
from google import genai
from google.genai import types

from models import CompanyProfile

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "company_profile.json")


def fetch_website_text(url: str, max_chars: int = 4000) -> str:
    """指定されたURLからWebページの主要テキストを抽出する"""
    if not url or url.strip() == "" or "example.com" in url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        logger.info(f"自社URLをスクレイピング中: {url}")
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
    current_challenges: Optional[dict] = None
) -> CompanyProfile:
    """自社URLと補足情報から、ビジネス成長・新機軸創出のための企業プロファイルを生成・キャッシュする"""
    os.makedirs(CACHE_DIR, exist_ok=True)

    # キャッシュが存在し、再生成フラグが立っていない場合はキャッシュを返す
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("キャッシュされた自社プロファイルを読み込みました。")
                profile = CompanyProfile(**data)
                # 直近の課題・KPIは動的に最新のものを注入
                profile.current_challenges = current_challenges
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
            response_schema=CompanyProfile,
            temperature=0.2
        )
    )

    profile_data = json.loads(response.text)
    profile = CompanyProfile(**profile_data)
    profile.current_challenges = current_challenges

    # キャッシュに保存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)
    logger.info("自社プロファイルをキャッシュに保存しました。")

    return profile
