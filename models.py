from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


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


class ArticleReference(BaseModel):
    """アイデアの着想元となった個別記事の情報"""
    title: str = Field(description="記事タイトル")
    url: str = Field(description="記事URL")
    source: str = Field(default="", description="情報ソース（メディア名やProduct Hunt等）")
    summary: str = Field(default="", description="記事の要約・ポイント（100〜150文字程度）")
    is_global: bool = Field(default=False, description="海外ソースかどうか")


class BizDevIdea(BaseModel):
    """深掘り分析された事業アイデア（複数記事のシナジーから創出）"""
    idea_title: str = Field(default="", description="アイデアのタイトル・企画名")
    
    # 複数記事の参照情報 & シナジー背景
    source_articles: List[ArticleReference] = Field(
        default_factory=list,
        description="着想元となった複数のニュース記事・先行事例"
    )
    synergy_rationale: str = Field(
        default="",
        description="これらの複数記事・動向をどう掛け合わせ、なぜ今このアイデアに至ったかのシナジー背景（点と点を繋いだ理由）"
    )
    
    # 課題と技術
    market_pain: str = Field(description="今世の中で浮き彫りになっている未解決の課題・ペイン")
    latest_tech: str = Field(description="活用されている最新の技術やアプローチ手法")
    
    # あなたならどう解決するか（ビジネス創出）
    solution_idea: str = Field(description="この課題に対し、あなたならどう解決するか（具体的なサービス・事業アイデア）")
    monetization_model: str = Field(description="お金を稼ぐためのビジネスモデル（課金形態、誰から収益を得るか）")
    kpi_impact: str = Field(description="自社の重点課題・KPIに対する具体的な貢献・インパクト")
    localization_opportunity: Optional[str] = Field(default=None, description="日本市場へのローカライズ機会・タイムマシン経営の視点")
    internal_next_action: str = Field(description="自社のアセットを活かして参入・PoCを進めるための検証論点・打ち手")

    # 守り・リスク評価（客観的批判・参謀視点）
    feasibility_rating: str = Field(description="実現性・開発難易度とその簡潔な理由")
    critical_risks: str = Field(description="最大の盲点・参入障壁・大手競合による模倣リスク、やらない理由")
    customer_readiness: str = Field(description="ターゲット顧客（小規模事業者・個人店）の受容性・導入障壁")
    objective_verdict: str = Field(description="客観的参謀としての辛口ジャッジ")

    # 定量評価スコア（グラフ・比較表用、1〜5段階）
    impact_score: int = Field(default=4, ge=1, le=5, description="自社KPIおよび事業インパクト度 (1〜5: 5が最大インパクト)")
    feasibility_score: int = Field(default=3, ge=1, le=5, description="実現容易性・実装難易度 (1〜5: 5が最も容易/低難易度)")
    speed_score: int = Field(default=3, ge=1, le=5, description="市場検証・立ち上げのスピード感 (1〜5: 5が最も即効性あり)")
    target_market_size: str = Field(default="中", description="市場規模感 (「特大」「大」「中」「ニッチ」)")

    # 後方互換用フィールド（古いレポートデータや単一記事参照用）
    article_title: Optional[str] = Field(default="", description="主要記事タイトル（後方互換用）")
    article_url: Optional[str] = Field(default="", description="主要記事URL（後方互換用）")
    is_global: bool = Field(default=False, description="海外先行事例を含むかどうか（後方互換用）")
    source_summary: Optional[str] = Field(default="", description="記事要約（後方互換用）")
    researched_facts: Optional[str] = Field(default=None, description="Web検索や本文分析から判明した市場背景やファクト・競合動向")

    @model_validator(mode="after")
    def sync_legacy_fields(self):
        """idea_titleとarticle_title、source_articlesと単一記事フィールド、スコアの相互補完"""
        # idea_title と article_title の同期
        if not self.idea_title and self.article_title:
            self.idea_title = self.article_title
        elif not self.article_title and self.idea_title:
            self.article_title = self.idea_title

        # source_articles がある場合、後方互換フィールドを自動設定
        if self.source_articles:
            if not self.article_url and self.source_articles[0].url:
                self.article_url = self.source_articles[0].url
            if not self.source_summary:
                self.source_summary = " / ".join([f"{a.title}: {a.summary[:60]}" for a in self.source_articles[:3]])
            if any(a.is_global for a in self.source_articles):
                self.is_global = True
        elif self.article_title and self.article_url:
            # 逆に古い単一記事データから source_articles を逆生成
            self.source_articles = [
                ArticleReference(
                    title=self.article_title,
                    url=self.article_url,
                    source="",
                    summary=self.source_summary or "",
                    is_global=self.is_global
                )
            ]

        # 過去データ用: feasibility_rating から feasibility_score の補正
        if self.feasibility_rating and self.feasibility_score == 3:
            if "高" in self.feasibility_rating or "容易" in self.feasibility_rating:
                self.feasibility_score = 4
            elif "低" in self.feasibility_rating or "困難" in self.feasibility_rating or "難" in self.feasibility_rating:
                self.feasibility_score = 2

        # 過去データ用: objective_verdict から impact_score や speed_score の補正
        if self.objective_verdict:
            if "即座に着手" in self.objective_verdict or "即着手" in self.objective_verdict:
                self.impact_score = max(self.impact_score, 5)
                self.speed_score = max(self.speed_score, 4)
            elif "限定検証" in self.objective_verdict:
                self.impact_score = max(self.impact_score, 4)
                self.speed_score = max(self.speed_score, 3)

        return self


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
