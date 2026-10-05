import json
import urllib.parse
import logging
import feedparser
from typing import List, Set, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

from models import NewsArticle, CompanyProfile
from gemini_helper import generate_with_fallback

logger = logging.getLogger(__name__)


def clean_html(raw_html: str) -> str:
    """HTMLタグを除去してプレーンテキストにする"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(strip=True)


def collect_product_hunt_items(max_items: int = 10, seen_links: Set[str] = None) -> List[NewsArticle]:
    """Product Huntの最新注目プロダクトフィードからSaaS・AIツールを収集する"""
    if seen_links is None:
        seen_links = set()

    articles: List[NewsArticle] = []
    ph_feed_url = "https://www.producthunt.com/feed"
    logger.info("Product Hunt (最新AI/SaaSプロダクト) を取得中...")

    try:
        feed = feedparser.parse(ph_feed_url)
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue

            title = entry.get("title", "")
            published = entry.get("published", "")
            raw_summary = entry.get("summary", "")
            summary = clean_html(raw_summary)

            article = NewsArticle(
                title=f"[Product Hunt] {title}",
                link=link,
                published=published,
                summary=summary,
                source="Product Hunt",
                is_global=True
            )
            seen_links.add(link)
            articles.append(article)

            if len(articles) >= max_items:
                break
    except Exception as e:
        logger.warning(f"Product Huntフィードの取得中にエラーが発生しました: {e}")

    logger.info(f"Product Huntから {len(articles)} 件の先行プロダクトを収集しました。")
    return articles


def collect_us_google_news(keywords: List[str], max_items: int = 10, seen_links: Set[str] = None) -> List[NewsArticle]:
    """米国のGoogle News (英語) からスモールビジネス向けAI/SaaS動向を収集する"""
    if seen_links is None:
        seen_links = set()

    articles: List[NewsArticle] = []
    for kw in keywords:
        if len(articles) >= max_items:
            break
        logger.info(f"米国ニュースキーワード '{kw}' で検索中...")
        encoded_kw = urllib.parse.quote(kw)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=en-US&gl=US&ceid=US:en"

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue

                title = entry.get("title", "")
                source = "US Tech News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                published = entry.get("published", "")
                raw_summary = entry.get("summary", "")
                summary = clean_html(raw_summary)

                article = NewsArticle(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary,
                    source=source,
                    is_global=True
                )
                seen_links.add(link)
                articles.append(article)

                if len(articles) >= max_items:
                    break
        except Exception as e:
            logger.warning(f"米国RSSの取得中にエラーが発生しました ({kw}): {e}")

    logger.info(f"米国Techニュースから {len(articles)} 件を収集しました。")
    return articles


def generate_issue_driven_queries(
    client: genai.Client,
    model_name: str,
    profile: CompanyProfile
) -> dict:
    """
    自社プロファイルの重点KPIや切実な課題（urgent_issues）を分析し、
    その課題解決・突破口となる最新技術・手法・先行事例を探索するための
    逆引き検索クエリ群（Goal-driven Queries）を動的生成する
    """
    kpi = ""
    issues = []
    if profile.current_challenges:
        kpi = profile.current_challenges.get("focus_kpi", "")
        issues = profile.current_challenges.get("urgent_issues", [])

    if not kpi and not issues:
        theme_str = ", ".join(profile.focus_themes) if profile.focus_themes else profile.core_business
        prompt_issues = f"- 事業成長テーマ: {theme_str}"
    else:
        issues_str = "\n".join([f"- 切実な課題: {iss}" for iss in issues])
        prompt_issues = f"- 重点KPI: {kpi}\n{issues_str}"

    system_instruction = """
あなたはビジネス課題を最先端テクノロジーと最新動向で打破するシニアリサーチディレクターです。
クライアントが直面している「切実な課題・ボトルネック」を解決・突破するための最新動向、AI/SaaS活用事例、
海外先行モデルを収集するための【逆引き検索クエリ（Goal-driven Queries）】を生成してください。

【生成のポイント】
- 単なる一般名詞（例:「AI 集客」）ではなく、「飛び込み営業 代替 AIリード獲得」「店舗 アイドルタイム 集客 生成AI」「中小企業 新規開拓 自動化」のように、課題の核心を突いた複合キーワードにしてください。
- 国内ニュース検索クエリ（日本語）を2〜3件、海外先行トレンドを探すための英語クエリを1〜2件生成してください。
- Google Search Grounding で直接深掘り調査するための「核心的な問い（deep_search_question）」を1件作成してください。
"""

    prompt = f"""
以下のクライアントの事業情報と直面している課題をもとに、課題解決のための逆引き検索クエリを生成してください。

【対象企業・事業】
- 名称: {profile.name}
- 主要事業: {profile.core_business}
- ターゲット顧客: {profile.target_customers}
- 保有アセット: {', '.join(profile.key_assets)}

【現在直面している切実な課題・重点KPI】
{prompt_issues}

以下のJSON形式で出力してください:
{{
  "research_intent": "この逆引きリサーチで解き明かしたい課題と探索の狙い（1〜2文）",
  "domestic_queries": ["国内ニュース検索クエリ1", "国内ニュース検索クエリ2"],
  "global_queries": ["英語ニュース検索クエリ1", "英語ニュース検索クエリ2"],
  "deep_search_question": "課題解決の成功事例や最新AIアプローチを調査するための核心的な問い"
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
        logger.warning(f"逆引きクエリ生成中にエラーが発生しました: {e}。フォールバッククエリを使用します。")
        fallback_kw = kpi or (issues[0] if issues else profile.core_business)
        return {
            "research_intent": f"{profile.name}の課題解決（{fallback_kw}）に向けた最新技術・施策の調査",
            "domestic_queries": [f"{fallback_kw} AI 活用", f"{profile.core_business} DX 解決事例"],
            "global_queries": ["AI solutions for small business customer acquisition"],
            "deep_search_question": f"{profile.core_business}における最新のAI・ITを活用した課題解決と売上向上の成功事例"
        }


def collect_issue_driven_research(
    client: genai.Client,
    model_name: str,
    profile: CompanyProfile,
    seen_links: Set[str] = None,
    max_items: int = 6
) -> Tuple[List[NewsArticle], str]:
    """
    自社課題から動的生成した逆引きクエリを用いて、
    ① 国内RSSニュース、② 海外RSSニュース、③ Google Search Groundingによるディープリサーチを実行する
    """
    if seen_links is None:
        seen_links = set()

    articles: List[NewsArticle] = []
    logger.info(f"\n🎯 自社課題を起点とした動的逆引きリサーチ（Pull型）を開始します: {profile.name}")

    query_data = generate_issue_driven_queries(client, model_name, profile)
    research_intent = query_data.get("research_intent", "課題解決のための先行事例リサーチ")
    domestic_queries = query_data.get("domestic_queries", [])
    global_queries = query_data.get("global_queries", [])
    deep_question = query_data.get("deep_search_question", "")

    logger.info(f"【逆引きリサーチ意図】: {research_intent}")
    logger.info(f"【生成された逆引きクエリ】: 国内={domestic_queries}, 海外={global_queries}")

    # 1. 国内ニュースRSS (逆引きクエリ)
    for kw in domestic_queries:
        if len(articles) >= max_items // 2:
            break
        logger.info(f"課題逆引きキーワード（国内） '{kw}' で検索中...")
        encoded_kw = urllib.parse.quote(kw)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ja&gl=JP&ceid=JP:ja"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:3]:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                title = entry.get("title", "")
                source = "国内課題特化ニュース"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()
                summary = clean_html(entry.get("summary", ""))

                articles.append(NewsArticle(
                    title=f"[🎯課題突破] {title}",
                    link=link,
                    published=entry.get("published", ""),
                    summary=summary,
                    source=source,
                    is_global=False,
                    is_issue_driven=True,
                    issue_context=research_intent
                ))
                seen_links.add(link)
        except Exception as e:
            logger.warning(f"逆引き国内RSS取得エラー ({kw}): {e}")

    # 2. 海外ニュースRSS (逆引き英語クエリ)
    for kw in global_queries:
        if len(articles) >= max_items - 1:
            break
        logger.info(f"課題逆引きキーワード（海外） '{kw}' で検索中...")
        encoded_kw = urllib.parse.quote(kw)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:2]:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                title = entry.get("title", "")
                source = "海外課題解決動向"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()
                summary = clean_html(entry.get("summary", ""))

                articles.append(NewsArticle(
                    title=f"[🎯海外先行解法] {title}",
                    link=link,
                    published=entry.get("published", ""),
                    summary=summary,
                    source=source,
                    is_global=True,
                    is_issue_driven=True,
                    issue_context=research_intent
                ))
                seen_links.add(link)
        except Exception as e:
            logger.warning(f"逆引き海外RSS取得エラー ({kw}): {e}")

    # 3. Google Search Grounding による「課題直結ディープリサーチ」
    if deep_question:
        try:
            logger.info(f"Gemini Google Search Groundingによる課題ディープリサーチ実行中: {deep_question}")
            search_prompt = f"""
あなたは卓越した事業開発・戦略コンサルタントです。以下の切実な課題に対し、Google検索ツールを活用して最新の突破口・実践例を調査してください。

【対象企業】
- 企業・事業: {profile.name} ({profile.core_business})
- ターゲット: {profile.target_customers}
- 直面している課題: {research_intent}

【調査課題】
{deep_question}

客観的なファクトベースで、以下の3点を300〜400文字程度で論理的に要約してください:
1. 先行企業や類似事業者がこの課題を解決するために採用している最新のAIツール・実践アプローチ
2. 従来のやり方（飛び込み、テレアポ、割引等）からどう脱却し成果を出しているかの具体例
3. {profile.name} のような事業者が今すぐ応用できる実用的なヒント・打ち手
"""
            search_config = types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.3
            )
            resp = generate_with_fallback(
                client=client,
                preferred_model=model_name,
                contents=search_prompt,
                config=search_config
            )
            if resp and resp.text:
                deep_insight_text = resp.text.strip()
                logger.info("課題直結ディープリサーチの完了に成功しました。")

                # 特化型ナレッジ記事として記事プールに追加
                today_str = datetime.now().strftime("%Y-%m-%d")
                virtual_article = NewsArticle(
                    title=f"[🎯課題突破リサーチ] {research_intent[:35]}の最新解法と先行事例",
                    link=f"https://news.google.com/search?q={urllib.parse.quote(deep_question[:40])}",
                    published=today_str,
                    summary=deep_insight_text[:200] + "...",
                    content=deep_insight_text,
                    source="AI課題逆引きディープリサーチ (Google Search)",
                    is_global=False,
                    is_issue_driven=True,
                    issue_context=research_intent
                )
                articles.insert(0, virtual_article)  # 最優先枠として先頭に配置
        except Exception as e:
            logger.warning(f"Google検索グラウンディングによる課題ディープリサーチ中にエラー: {e}")

    logger.info(f"🎯 課題逆引きリサーチ完了: 合計 {len(articles)} 件の課題直結インサイト・記事を収集しました。")
    return articles, research_intent


def collect_news(
    keywords: List[str],
    max_total_articles: int = 25,
    global_config: dict = None,
    profile: Optional[CompanyProfile] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = "gemini-2.5-flash"
) -> List[NewsArticle]:
    """
    国内キーワード検索＋海外先行事例に加え、
    自社課題を起点とした動的逆引きリサーチ（Pull型）を統合収集する
    """
    articles: List[NewsArticle] = []
    seen_links: Set[str] = set()

    # 1. 自社課題を起点とした動的逆引きリサーチ（最優先）
    if profile and api_key:
        try:
            client = genai.Client(api_key=api_key)
            issue_articles, _ = collect_issue_driven_research(
                client=client,
                model_name=model_name or "gemini-2.5-flash",
                profile=profile,
                seen_links=seen_links,
                max_items=8
            )
            articles.extend(issue_articles)
        except Exception as e:
            logger.warning(f"動的課題逆引きリサーチの実行中に警告: {e}")

    issue_count = len(articles)

    # 2. 通常の国内ニュースの収集 (Push型)
    for kw in keywords:
        logger.info(f"国内キーワード '{kw}' でニュースを検索中...")
        encoded_kw = urllib.parse.quote(kw)
        # Google News RSS (日本語)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ja&gl=JP&ceid=JP:ja"

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue

                title = entry.get("title", "")
                source = "Web News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                published = entry.get("published", "")
                raw_summary = entry.get("summary", "")
                summary = clean_html(raw_summary)

                article = NewsArticle(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary,
                    source=source,
                    is_global=False,
                    is_issue_driven=False
                )
                seen_links.add(link)
                articles.append(article)

                if len(articles) >= max_total_articles:
                    break
        except Exception as e:
            logger.warning(f"RSSの取得中にエラーが発生しました ({kw}): {e}")

        if len(articles) >= max_total_articles:
            break

    domestic_count = len(articles) - issue_count

    # 3. 海外先行事例の収集（有効な場合）
    global_count = 0
    if global_config and global_config.get("enabled", False):
        logger.info("\n--- [海外トレンド・先行SaaS収集] ---")
        max_global = global_config.get("max_articles_to_collect", 10)

        # 3-A: Product Hunt
        if global_config.get("enable_product_hunt", True):
            ph_items = collect_product_hunt_items(max_items=max(3, max_global // 2), seen_links=seen_links)
            articles.extend(ph_items)

        # 3-B: 米国Google News
        us_keywords = global_config.get("us_keywords", ["AI tool for small business", "SMB SaaS AI"])
        if us_keywords:
            us_items = collect_us_google_news(keywords=us_keywords, max_items=max_global, seen_links=seen_links)
            articles.extend(us_items)

        global_count = len(articles) - (domestic_count + issue_count)

    logger.info(f"合計 {len(articles)} 件のニュース・先行事例を収集しました (🎯課題逆引き: {issue_count}件, 国内: {domestic_count}件, 海外: {global_count}件)")
    return articles
