from typing import List, Optional
from pydantic import BaseModel, Field


class CompanyProfileBase(BaseModel):
    """自社・ユーザーのプロファイル情報（AI分析・生成対象）"""
    name: str = Field(description="会社名または事業部名")
    core_business: str = Field(description="主要な事業ドメインや提供価値")
    target_customers: str = Field(description="主なターゲット顧客層")
    key_assets: List[str] = Field(description="保有する強み・アセット（顧客網、技術力、データ等）")
    focus_themes: List[str] = Field(description="関心・注力したいテーマや課題領域")
    raw_summary: str = Field(description="プロファイル全体のサマリー")


class CompanyProfile(CompanyProfileBase):
    """自社・ユーザーのプロファイル情報（動的課題・KPIを含む完全版）"""
    current_challenges: Optional[dict] = Field(default=None, description="直近の重点課題や注力KPI")


class NewsArticle(BaseModel):
    """収集したニュース記事のモデル"""
    title: str
    link: str
    published: str
    summary: str
    source: str
    content: Optional[str] = Field(default=None, description="スクレイピングした記事本文")
    is_global: bool = Field(default=False, description="海外ソース（Product Hunt / 米国Tech動向）かどうか")


class ArticleEvaluation(BaseModel):
    """一次スクリーニングでの評価"""
    article_index: int
    score: int = Field(description="1〜10の総合スコア")
    relevance_reason: str = Field(description="自社ビジネス成長との関連性・着目すべき理由")


class BizDevIdea(BaseModel):
    """深掘り分析された事業アイデア"""
    article_title: str
    article_url: str
    is_global: bool = Field(default=False, description="海外先行事例かどうか")
    source_summary: str = Field(description="記事の客観的ファクト・要約")
    researched_facts: Optional[str] = Field(default=None, description="Web検索や本文分析から判明した市場背景やファクト・競合動向")
    localization_opportunity: Optional[str] = Field(default=None, description="日本市場へのローカライズ機会・タイムマシン経営の視点（国内小規模店向け応用案）")
    
    # 課題と技術
    market_pain: str = Field(description="今世の中で浮き彫りになっている未解決の課題・ペイン")
    latest_tech: str = Field(description="活用されている最新の技術やアプローチ手法")
    
    # あなたならどう解決するか（ビジネス創出）
    solution_idea: str = Field(description="この課題に対し、あなたならどう解決するか（具体的なサービス・事業アイデア）")
    monetization_model: str = Field(description="お金を稼ぐためのビジネスモデル（課金形態、誰から収益を得るか）")
    kpi_impact: str = Field(description="自社の重点課題・KPIに対する具体的な貢献・インパクト")
    internal_next_action: str = Field(description="自社のアセットを活かして参入・PoCを進めるための検証論点・打ち手")

    # 守り・リスク評価（客観的批判・参謀視点）
    feasibility_rating: str = Field(description="実現性・開発難易度（例: '高 (既存技術で即PoC可能)' / '中' / '低 (要大規模開発)' とその簡潔な理由）")
    critical_risks: str = Field(description="最大の盲点・参入障壁・大手競合による模倣リスク、やらない理由")
    customer_readiness: str = Field(description="ターゲット顧客（小規模事業者・個人店）の受容性・導入障壁（IT苦手、忙しさ等）")
    objective_verdict: str = Field(description="客観的参謀としての辛口ジャッジ（今すぐ着手すべきか、見送るべきか、どう限定検証すべきか）")


class WeeklyReport(BaseModel):
    """最終的な週次レポート"""
    report_title: str
    generated_at: str
    company_name: str
    focus_kpi: Optional[str] = Field(default=None, description="対象期間の重点KPI")
    ideas: List[BizDevIdea]
    overall_trend_comment: str = Field(description="今回の収集から見えるマクロトレンド・総括コメント")


# エイリアス
GrowthIdea = BizDevIdea
