from typing import List, Optional
from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """自社・ユーザーのプロファイル情報"""
    name: str = Field(description="会社名または事業部名")
    core_business: str = Field(description="主要な事業ドメインや提供価値")
    target_customers: str = Field(description="主なターゲット顧客層")
    key_assets: List[str] = Field(description="保有する強み・アセット（顧客網、技術力、データ等）")
    focus_themes: List[str] = Field(description="関心・注力したいテーマや課題領域")
    raw_summary: str = Field(description="プロファイル全体のサマリー")


class NewsArticle(BaseModel):
    """収集したニュース記事のモデル"""
    title: str
    link: str
    published: str
    summary: str
    source: str


class ArticleEvaluation(BaseModel):
    """一次スクリーニングでの評価"""
    article_index: int
    score: int = Field(description="1〜10の総合スコア")
    relevance_reason: str = Field(description="自社事業開発との関連性・着目すべき理由")


class BizDevIdea(BaseModel):
    """深掘り分析された事業アイデア"""
    article_title: str
    article_url: str
    source_summary: str = Field(description="記事の客観的ファクト・要約")
    
    # 課題と技術
    market_pain: str = Field(description="今世の中で浮き彫りになっている未解決の課題・ペイン")
    latest_tech: str = Field(description="活用されている最新の技術やアプローチ手法")
    
    # あなたならどう解決するか（ビジネス創出）
    solution_idea: str = Field(description="この課題に対し、あなたならどう解決するか（具体的なサービス・事業アイデア）")
    monetization_model: str = Field(description="お金を稼ぐためのビジネスモデル（課金形態、誰から収益を得るか）")
    internal_next_action: str = Field(description="自社のアセットを活かして参入・PoCを進めるための検証論点・打ち手")


class WeeklyReport(BaseModel):
    """最終的な週次レポート"""
    report_title: str
    generated_at: str
    company_name: str
    ideas: List[BizDevIdea]
    overall_trend_comment: str = Field(description="今回の収集から見えるマクロトレンド・総括コメント")
