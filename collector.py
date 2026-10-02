import urllib.parse
import logging
import feedparser
from typing import List, Set
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from models import NewsArticle

logger = logging.getLogger(__name__)


def clean_html(raw_html: str) -> str:
    """HTMLタグを除去してプレーンテキストにする"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(strip=True)


def collect_news(keywords: List[str], max_total_articles: int = 25) -> List[NewsArticle]:
    """
    指定されたキーワードでGoogle News RSS等からニュース記事を収集する
    """
    articles: List[NewsArticle] = []
    seen_links: Set[str] = set()

    for kw in keywords:
        logger.info(f"キーワード '{kw}' でニュースを検索中...")
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
                # Google Newsのタイトルは末尾に " - メディア名" がつくことが多い
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
                    source=source
                )
                seen_links.add(link)
                articles.append(article)

                if len(articles) >= max_total_articles:
                    break
        except Exception as e:
            logger.warning(f"RSSの取得中にエラーが発生しました ({kw}): {e}")

        if len(articles) >= max_total_articles:
            break

    logger.info(f"合計 {len(articles)} 件のニュースを収集しました。")
    return articles
