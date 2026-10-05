import os
import json
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

PROFILES_DIR = "profiles"
CONFIG_PATH = "config.yaml"

# サンプルプリセット定義
DEFAULT_PRESETS = [
    {
        "id": "haveasite",
        "name": "HaveASite（ハブアサイト）",
        "url": "https://haveasite.com/",
        "notes": (
            "【サービス概要】\n"
            "「契約前に実物を作るサブスク型ホームページ制作」\n"
            "初期費用0円・月額8,800円（税込）で、個人店・小規模事業者向けに初期0円で動く実物サンプルを先行提示し、\n"
            "ドメイン・サーバー・月5回までの修正更新まで丸投げで対応するサービス。最低契約期間なし。\n\n"
            "【ターゲット顧客】\n"
            "個人店・小規模事業者（飲食店、美容室・サロン、整体院、工務店、個人商店、士業など）。\n"
            "「SNSはあるが公式HPがない」「初期費用数十万円は払えない」「ITが苦手で丸投げしたい」「準備に時間をかけられない」店舗オーナー。\n\n"
            "【保有アセット・強み】\n"
            "- 「契約前に実物サンプルを作る」強力な成約・信頼獲得プロセス\n"
            "- 初期0円・月額8,800円の圧倒的コストパフォーマンスと明瞭なサブスクモデル\n"
            "- スモールビジネス特化の企画・デザイン・運用保守のワンストップ体制\n\n"
            "【今後の検討・注力テーマ】\n"
            "1. 生成AIを活用したHP制作・コンテンツ生成の自動化・工数削減（利益率向上）\n"
            "2. 個人店向けの集客支援（MEO/Googleビジネスプロフィール連携、LINE公式、AI口コミ返信、AI予約等）の追加オプション・クロスセル\n"
            "3. 小規模事業者が直面する「人手不足」「集客難」「ITリテラシー格差」を解決する新サービス・新マネタイズモデルの創出"
        ),
        "current_challenges": {
            "focus_kpi": "顧客の獲得",
            "urgent_issues": [
                "飛び込み営業をしているが、顧客が取れない。InstagramなどのSNSが主流の今、HPを必要としていないオーナーが多い。"
            ]
        },
        "resource_constraints": {
            "weekly_hours": "週5〜10時間",
            "budget": "月1〜3万円",
            "technical_skill": "ノーコード・AIツール活用可能",
            "team_size": "1〜2名"
        },
        "keywords": [
            "店舗 DX AI",
            "小規模事業者 集客 AI",
            "Web制作 生成AI",
            "中小企業 IT導入 課題"
        ]
    },
    {
        "id": "local_cafe",
        "name": "自家焙煎カフェ＆ベーカリー (サンプル)",
        "url": "https://example.com/cafe-bakery",
        "notes": (
            "【店舗概要】\n"
            "住宅街に位置するスペシャルティコーヒーと焼きたてパンの個人カフェ。\n"
            "座席数18席。オーナーシェフとアルバイト2名で運営。\n\n"
            "【ターゲット顧客】\n"
            "近隣の30〜50代ファミリー層、在宅ワーカー、コーヒー愛好家。\n\n"
            "【保有アセット・強み】\n"
            "- 自家焙煎コーヒーの味とパンの品質に対する高い常連客リピート率\n"
            "- 温かみのある内装と居心地の良さ\n"
            "- Instagramフォロワー約1,500人\n\n"
            "【検討・注力テーマ】\n"
            "1. 平日アイドルタイム（14:00〜17:00）の売上底上げ\n"
            "2. コーヒー豆や焼き菓子のテイクアウト・定期通販（サブスク）の立ち上げ\n"
            "3. 常連客向けのLINEショップカードやAIを活用した予約・取り置きの仕組み化"
        ),
        "current_challenges": {
            "focus_kpi": "平日アイドルタイムの売上向上 & リピート率改善",
            "urgent_issues": [
                "土日は満席だが平日の昼下がりの客足が極端に落ちる。",
                "近隣に大手コーヒーチェーンができ、テイクアウト利用客が流出している。",
                "SNS発信はしているが、実際の平日の集客に結びついていない。"
            ]
        },
        "resource_constraints": {
            "weekly_hours": "週2〜3時間（仕込み合間や休日）",
            "budget": "完全ゼロ〜月1万円未満（無料ツール中心）",
            "technical_skill": "非IT・スマホ中心（Instagram/LINEは可）",
            "team_size": "1人（ワンオペ＋パート2名）"
        },
        "keywords": [
            "飲食店 DX AI",
            "カフェ 集客 AI",
            "ローカルビジネス リピート促進",
            "店舗 アイドルタイム 集客"
        ]
    },
    {
        "id": "ai_saas_creator",
        "name": "個人開発AIスタジオ (新規事業立ち上げサンプル)",
        "url": "https://example.com/ai-studio",
        "notes": (
            "【事業構想】\n"
            "フルスタックエンジニア（個人）が立ち上げ準備中の、中小企業・特定業界向けマイクロAIツール群の企画・開発・運営。\n\n"
            "【ターゲット顧客】\n"
            "人手不足に悩むスモールビジネス（士業、不動産仲介、採用代行など）。\n\n"
            "【保有アセット・強み】\n"
            "- LLM（Gemini/OpenAI）を活用した迅速なプロトタイプ開発力とアジリティ\n"
            "- 個人開発ならではの低固定費と素早い方向転換（ピボット）\n\n"
            "【検討・注力テーマ】\n"
            "1. 誰もが参入できる汎用ラッパーではなく、特定業界の深いペインを突いたバーティカルAIツールの発掘\n"
            "2. 最初の有料顧客（デザインパートナー）3社を獲得し、PMF（プロダクトマーケットフィット）を検証する"
        ),
        "current_challenges": {
            "focus_kpi": "最初の有料顧客3社の獲得 (PMF検証)",
            "urgent_issues": [
                "技術はあるが、スモールビジネスの現場で「本当にお金を払ってでも解決したい切実なペイン」が絞り込めていない。",
                "大手のAIツールや無料ツールとの差別化ポイントが言語化できていない。"
            ]
        },
        "resource_constraints": {
            "weekly_hours": "週15〜20時間（副業〜専業）",
            "budget": "月1〜3万円（API費用・サーバー代）",
            "technical_skill": "エンジニア（自社開発・API実装可能）",
            "team_size": "1人（個人開発）"
        },
        "keywords": [
            "AI マイクロSaaS",
            "スモールビジネス 自動化 AI",
            "バーティカルAI 課題解決",
            "SMB AIツール PMF"
        ]
    }
]


def sanitize_profile_id(raw_id: str) -> str:
    """プロファイルIDを安全なファイル名形式にサニタイズする"""
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_id.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or f"profile_{int(datetime.now().timestamp())}"


def ensure_profiles_dir() -> None:
    """profilesディレクトリと初期プリセットを作成・マイグレーションする"""
    os.makedirs(PROFILES_DIR, exist_ok=True)

    # 既存の config.yaml からのインポートまたはデフォルトプリセットの配置
    preset_ids = [p["id"] for p in DEFAULT_PRESETS]
    for preset in DEFAULT_PRESETS:
        p_id = preset["id"]
        filepath = os.path.join(PROFILES_DIR, f"{p_id}.json")
        if not os.path.exists(filepath):
            # haveasite の場合、config.yaml の最新値があればそちらを優先
            if p_id == "haveasite" and os.path.exists(CONFIG_PATH):
                try:
                    import yaml
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                    comp = cfg.get("company", {})
                    if comp and comp.get("name"):
                        preset["name"] = comp.get("name", preset["name"])
                        preset["url"] = comp.get("url", preset["url"])
                        preset["notes"] = comp.get("notes", preset["notes"])
                        if comp.get("current_challenges"):
                            preset["current_challenges"] = comp.get("current_challenges")
                    news_kws = cfg.get("news", {}).get("keywords", [])
                    if news_kws:
                        preset["keywords"] = news_kws
                except Exception as e:
                    logger.warning(f"config.yamlからのプロファイル初期インポート中に警告: {e}")

            preset["created_at"] = datetime.now().isoformat()
            preset["updated_at"] = datetime.now().isoformat()
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(preset, f, ensure_ascii=False, indent=2)
                logger.info(f"初期プロファイルを生成しました: {filepath}")
            except Exception as e:
                logger.error(f"初期プロファイルの保存に失敗: {e}")
        else:
            # 既存ファイルのマイグレーション（resource_constraints が未設定ならプリセットから補完）
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "resource_constraints" not in existing and "resource_constraints" in preset:
                    existing["resource_constraints"] = preset["resource_constraints"]
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(existing, f, ensure_ascii=False, indent=2)
                    logger.info(f"プロファイル {p_id} にリソース制約を自動マイグレーションしました。")
            except Exception:
                pass


def list_profiles() -> List[Dict]:
    """登録されている全プロファイルのサマリー一覧を取得する"""
    ensure_profiles_dir()
    profiles = []
    
    for filename in os.listdir(PROFILES_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(PROFILES_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            pid = data.get("id") or os.path.splitext(filename)[0]
            profiles.append({
                "id": pid,
                "name": data.get("name", "名称未設定"),
                "url": data.get("url", ""),
                "focus_kpi": data.get("current_challenges", {}).get("focus_kpi", ""),
                "urgent_issues_count": len(data.get("current_challenges", {}).get("urgent_issues", [])),
                "keywords_count": len(data.get("keywords", [])),
                "updated_at": data.get("updated_at", "")
            })
        except Exception as e:
            logger.warning(f"プロファイル読み込みエラー ({filename}): {e}")

    # ID順（haveasiteを先頭に）
    profiles.sort(key=lambda p: (0 if p["id"] == "haveasite" else 1, p["name"]))
    return profiles


def get_profile(profile_id: str) -> Optional[Dict]:
    """指定されたIDのプロファイルの完全データを取得する"""
    ensure_profiles_dir()
    clean_id = sanitize_profile_id(profile_id)
    filepath = os.path.join(PROFILES_DIR, f"{clean_id}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["id"] = clean_id

        # resource_constraints のフォールバック保証
        if not data.get("resource_constraints"):
            preset = next((p for p in DEFAULT_PRESETS if p["id"] == clean_id), None)
            if preset and preset.get("resource_constraints"):
                data["resource_constraints"] = preset["resource_constraints"]
            else:
                data["resource_constraints"] = {
                    "weekly_hours": "週5〜10時間",
                    "budget": "月1〜3万円",
                    "technical_skill": "ノーコード・AI活用",
                    "team_size": "1〜2名"
                }
        return data
    except Exception as e:
        logger.error(f"プロファイルの取得に失敗 ({profile_id}): {e}")
        return None


def save_profile(profile_data: Dict) -> Dict:
    """プロファイルを新規作成または更新して保存する"""
    ensure_profiles_dir()
    raw_id = profile_data.get("id") or profile_data.get("name", "profile")
    pid = sanitize_profile_id(raw_id)
    profile_data["id"] = pid

    now_iso = datetime.now().isoformat()
    if not profile_data.get("created_at"):
        profile_data["created_at"] = now_iso
    profile_data["updated_at"] = now_iso

    # バリデーション補正
    if "current_challenges" not in profile_data or not isinstance(profile_data["current_challenges"], dict):
        profile_data["current_challenges"] = {"focus_kpi": "", "urgent_issues": []}
    if "resource_constraints" not in profile_data or not isinstance(profile_data["resource_constraints"], dict):
        profile_data["resource_constraints"] = {
            "weekly_hours": "週5〜10時間",
            "budget": "月1〜3万円",
            "technical_skill": "ノーコード・AI活用",
            "team_size": "1〜2名"
        }
    if "keywords" not in profile_data or not isinstance(profile_data["keywords"], list):
        profile_data["keywords"] = []

    filepath = os.path.join(PROFILES_DIR, f"{pid}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

    logger.info(f"プロファイルを保存しました: {pid} ({profile_data.get('name')})")

    # もし現在のアクティブプロファイルと同じなら config.yaml も同期更新
    active_id = get_active_profile_id()
    if active_id == pid:
        sync_profile_to_config(pid)

    return profile_data


def duplicate_profile(source_id: str, new_name: Optional[str] = None) -> Optional[Dict]:
    """既存のプロファイルを複製して新しいプロファイルを作成する"""
    src = get_profile(source_id)
    if not src:
        return None

    new_data = dict(src)
    clean_base_id = sanitize_profile_id(source_id)
    timestamp_str = datetime.now().strftime("%m%d_%H%M")
    new_data["id"] = f"{clean_base_id}_copy_{timestamp_str}"
    new_data["name"] = new_name or f"{src.get('name', 'プロファイル')} (コピー)"
    new_data["created_at"] = datetime.now().isoformat()
    new_data["updated_at"] = datetime.now().isoformat()

    return save_profile(new_data)


def delete_profile(profile_id: str) -> bool:
    """プロファイルを削除する（アクティブな場合は直ちに別プロファイルへフォールバック）"""
    ensure_profiles_dir()
    clean_id = sanitize_profile_id(profile_id)
    filepath = os.path.join(PROFILES_DIR, f"{clean_id}.json")

    if not os.path.exists(filepath):
        return False

    # プロファイルが1つだけの場合は削除不可
    all_p = list_profiles()
    if len(all_p) <= 1:
        raise ValueError("最後の1つのプロファイルは削除できません。")

    try:
        os.remove(filepath)
        logger.info(f"プロファイルを削除しました: {clean_id}")

        # アクティブプロファイルだった場合、別のプロファイルをアクティブに設定
        active_id = get_active_profile_id()
        if active_id == clean_id:
            remaining = [p["id"] for p in list_profiles() if p["id"] != clean_id]
            if remaining:
                set_active_profile_id(remaining[0])
        return True
    except Exception as e:
        logger.error(f"プロファイルの削除に失敗 ({clean_id}): {e}")
        return False


def get_active_profile_id() -> str:
    """現在アクティブなプロファイルIDを取得する（config.yamlから読み込み、無ければhaveasite）"""
    ensure_profiles_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            act_id = cfg.get("active_profile_id")
            if act_id and os.path.exists(os.path.join(PROFILES_DIR, f"{sanitize_profile_id(act_id)}.json")):
                return sanitize_profile_id(act_id)
        except Exception:
            pass

    # フォールバック
    all_p = list_profiles()
    if all_p:
        return all_p[0]["id"]
    return "haveasite"


def set_active_profile_id(profile_id: str) -> bool:
    """アクティブなプロファイルを切り替え、config.yaml と同期する"""
    ensure_profiles_dir()
    clean_id = sanitize_profile_id(profile_id)
    filepath = os.path.join(PROFILES_DIR, f"{clean_id}.json")
    if not os.path.exists(filepath):
        return False

    sync_profile_to_config(clean_id)
    return True


def sync_profile_to_config(profile_id: str) -> bool:
    """特定プロファイルの内容を config.yaml の company & news.keywords に同期反映する"""
    target_prof = get_profile(profile_id)
    if not target_prof:
        return False

    if not os.path.exists(CONFIG_PATH):
        return False

    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        cfg["active_profile_id"] = profile_id
        if "company" not in cfg:
            cfg["company"] = {}
        cfg["company"]["name"] = target_prof.get("name", "")
        cfg["company"]["url"] = target_prof.get("url", "")
        cfg["company"]["notes"] = target_prof.get("notes", "")
        cfg["company"]["current_challenges"] = target_prof.get("current_challenges", {
            "focus_kpi": "",
            "urgent_issues": []
        })
        cfg["company"]["resource_constraints"] = target_prof.get("resource_constraints", {
            "weekly_hours": "週5〜10時間",
            "budget": "月1〜3万円",
            "technical_skill": "ノーコード・AI活用",
            "team_size": "1〜2名"
        })

        # プロファイル固有のキーワードがあればニュース設定にも同期
        prof_kws = target_prof.get("keywords")
        if prof_kws and isinstance(prof_kws, list) and len(prof_kws) > 0:
            if "news" not in cfg:
                cfg["news"] = {}
            cfg["news"]["keywords"] = prof_kws

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

        logger.info(f"config.yaml をプロファイル '{profile_id}' ({target_prof.get('name')}) と同期しました。")
        return True
    except Exception as e:
        logger.error(f"config.yaml へのプロファイル同期に失敗: {e}")
        return False
