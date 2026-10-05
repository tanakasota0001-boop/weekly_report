#!/usr/bin/env python3
"""
ビジネス成長AIエージェント - Web UI / ダッシュボードサーバー
Python標準ライブラリ（http.server）のみで動作し、追加パッケージ不要で軽快に動作します。
"""

import os
import sys
import json
import logging
import threading
import time
import webbrowser

# Windows環境でのUnicodeEncodeError対策
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
try:
    from http.server import ThreadingHTTPServer as ServerClass
except ImportError:
    from http.server import HTTPServer as ServerClass
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(override=False):
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        parts = line.split("=", 1)
                        k = parts[0].strip()
                        v = parts[1].strip().strip("'\"")
                        if override or k not in os.environ:
                            os.environ[k] = v

try:
    import yaml
except ImportError:
    yaml = None

import profile_manager
from notifier import (
    save_markdown_report,
    load_report_data,
    list_saved_reports,
    send_via_gmail,
    format_report_to_markdown
)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("GrowthDashboardServer")

CONFIG_PATH = "config.yaml"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def load_config_dict() -> dict:
    """設定ファイルを辞書として安全に読み込む（PyYAML未導入時も部分読み込み対応）"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    if yaml is not None:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"YAML読み込みエラー: {e}")
            return {}

    # PyYAML未導入時のフォールバック
    cfg = {
        "company": {"name": "", "url": "", "notes": "", "current_challenges": {"focus_kpi": "", "urgent_issues": []}},
        "news": {"keywords": [], "global_sources": {"enabled": True, "enable_product_hunt": True}},
        "notification": {"channel": "gmail", "gmail": {"to_email": ""}}
    }
    current_section = None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and not line.startswith("\t") and stripped.endswith(":"):
                    current_section = stripped.rstrip(":")
                    continue
                if current_section == "company":
                    if stripped.startswith("name:"):
                        cfg["company"]["name"] = stripped.split(":", 1)[1].strip().strip('"\'')
                    elif stripped.startswith("url:"):
                        cfg["company"]["url"] = stripped.split(":", 1)[1].strip().strip('"\'')
                elif current_section == "news":
                    if stripped.startswith("- "):
                        kw = stripped[2:].strip().strip('"\'')
                        if kw and kw not in cfg["news"]["keywords"]:
                            cfg["news"]["keywords"].append(kw)
                elif current_section == "notification":
                    if stripped.startswith("channel:"):
                        cfg["notification"]["channel"] = stripped.split(":", 1)[1].strip().strip('"\'')
                    elif stripped.startswith("to_email:"):
                        cfg["notification"]["gmail"]["to_email"] = stripped.split(":", 1)[1].strip().strip('"\'')
                if stripped.startswith("focus_kpi:"):
                    cfg["company"]["current_challenges"]["focus_kpi"] = stripped.split(":", 1)[1].strip().strip('"\'')
    except Exception:
        pass
    return cfg


def save_config_dict(data: dict) -> None:
    """設定ファイルを保存する"""
    if yaml is not None:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    else:
        raise ImportError("設定ファイルの保存には PyYAML が必要です ('pip install pyyaml')。")


# バックグラウンド実行タスクの状態管理
class TaskManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"  # idle, running, completed, error
        self.current_step = 0
        self.total_steps = 4
        self.step_name = ""
        self.progress = 0
        self.logs = []
        self.report_id = None
        self.error = None
        self.start_time = None
        self.end_time = None

    def add_log(self, message: str, level: str = "INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = {"time": now_str, "level": level, "message": message}
        with self.lock:
            self.logs.append(entry)
            # 最大500件まで保持
            if len(self.logs) > 500:
                self.logs.pop(0)

    def set_step(self, step: int, name: str, progress: int):
        with self.lock:
            self.current_step = step
            self.step_name = name
            self.progress = progress
        self.add_log(f"[{step}/{self.total_steps}] {name} を開始します...", "INFO")

    def to_dict(self):
        with self.lock:
            return {
                "status": self.status,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "step_name": self.step_name,
                "progress": self.progress,
                "logs": list(self.logs),
                "report_id": self.report_id,
                "error": self.error,
                "start_time": self.start_time,
                "end_time": self.end_time,
            }


task_manager = TaskManager()


def run_generation_task(options: dict):
    """別スレッドでレポート生成パイプラインを実行する（指定プロファイル対応）"""
    dry_run = options.get("dry_run", False)
    refresh_profile = options.get("refresh_profile", False)
    override_kpi = options.get("override_kpi", "").strip()
    target_profile_id = options.get("profile_id", "").strip() or profile_manager.get_active_profile_id()

    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY", "")

    with task_manager.lock:
        task_manager.status = "running"
        task_manager.error = None
        task_manager.report_id = None
        task_manager.logs.clear()
        task_manager.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_manager.progress = 5

    task_manager.add_log(f"レポート生成タスクを開始しました (対象プロファイル: {target_profile_id})。", "INFO")

    try:
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY が設定されていません。.env ファイルを確認してください。")

        if yaml is None:
            raise ImportError("PyYAML がインストールされていません。'pip install -r requirements.txt' を実行してください。")

        if not os.path.exists(CONFIG_PATH):
            raise FileNotFoundError(f"設定ファイル {CONFIG_PATH} が存在しません。")

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        try:
            from profiler import build_company_profile
            from collector import collect_news
            from analyzer import generate_growth_analysis
        except ImportError as e:
            raise ImportError(f"必要なライブラリが見つかりません ({e})。'pip install -r requirements.txt' を実行してください。")

        model_name = config.get("model", {}).get("name", "gemini-2.5-flash")
        comp_cfg = config.get("company", {})
        news_cfg = config.get("news", {})
        research_cfg = config.get("research", {})
        notif_cfg = config.get("notification", {})

        # プロファイルデータのロード
        prof_data = profile_manager.get_profile(target_profile_id)
        if prof_data:
            comp_cfg = {
                "name": prof_data.get("name", comp_cfg.get("name")),
                "url": prof_data.get("url", comp_cfg.get("url")),
                "notes": prof_data.get("notes", comp_cfg.get("notes")),
                "current_challenges": prof_data.get("current_challenges", comp_cfg.get("current_challenges")),
                "resource_constraints": prof_data.get("resource_constraints", comp_cfg.get("resource_constraints")),
            }
            if prof_data.get("keywords"):
                news_cfg["keywords"] = prof_data["keywords"]
            task_manager.add_log(f"プロファイル情報読込: 『{prof_data.get('name')}』", "INFO")
        else:
            task_manager.add_log(f"プロファイル '{target_profile_id}' が見つからないため config.yaml 設定を使用します。", "WARNING")

        current_challenges = comp_cfg.get("current_challenges", {})
        if override_kpi:
            current_challenges["focus_kpi"] = override_kpi
            task_manager.add_log(f"重点KPIが一時オーバーライドされました: {override_kpi}", "INFO")

        # Step 1: プロファイル準備
        task_manager.set_step(1, "自社プロファイルの準備", 15)
        profile = build_company_profile(
            api_key=api_key,
            model_name=model_name,
            name=comp_cfg.get("name", "自社"),
            url=comp_cfg.get("url", ""),
            notes=comp_cfg.get("notes", ""),
            force_refresh=refresh_profile,
            current_challenges=current_challenges,
            resource_constraints=comp_cfg.get("resource_constraints"),
            profile_id=target_profile_id
        )
        rc_info = ""
        if profile.resource_constraints:
            rc = profile.resource_constraints
            rc_info = f" [リソース: {rc.get('weekly_hours', '')}/{rc.get('budget', '')}/{rc.get('technical_skill', '')}]"
        task_manager.add_log(f"プロファイル確認完了: {profile.name}{rc_info}", "INFO")

        # Step 2: ニュース収集 & 課題逆引きリサーチ
        task_manager.set_step(2, "自社課題逆引きリサーチ ＆ 国内・海外動向収集", 35)
        keywords = news_cfg.get("keywords", ["生成AI ビジネス", "DX 新規事業"])
        max_collect = news_cfg.get("max_articles_to_collect", 20)
        global_cfg = news_cfg.get("global_sources", {})

        kpi_label = current_challenges.get("focus_kpi", "未設定")
        task_manager.add_log(f"自社の切実な課題（KPI: {kpi_label}）を起点に、最新技術・代替手法の逆引きリサーチ（Pull型）を開始します...", "INFO")
        articles = collect_news(
            keywords=keywords,
            max_total_articles=max_collect,
            global_config=global_cfg,
            profile=profile,
            api_key=api_key,
            model_name=model_name
        )
        if not articles:
            raise ValueError("収集できたニュース記事が0件でした。キーワード設定を見直してください。")
        
        issue_cnt = sum(1 for a in articles if getattr(a, "is_issue_driven", False))
        task_manager.add_log(f"合計 {len(articles)} 件を収集完了 (🎯自社課題逆引き: {issue_cnt}件, 国内外動向: {len(articles) - issue_cnt}件)", "INFO")

        # Step 3: 分析 & アイデア生成
        task_manager.set_step(3, "本文スクレイピング・Web検索グラウンディング・戦略立案", 60)
        top_n = news_cfg.get("top_articles_to_report", 3)
        task_manager.add_log(f"上位 {top_n} 件を厳選し、深掘り分析と「攻め（事業案）」＆「守り（リスク・客観的批判）」を立案中...", "INFO")

        report = generate_growth_analysis(
            api_key=api_key,
            model_name=model_name,
            articles=articles,
            profile=profile,
            top_n=top_n,
            research_config=research_cfg
        )
        task_manager.add_log(f"戦略レポート生成完了: 『{report.report_title}』 (アイデア数: {len(report.ideas)}件)", "INFO")

        # Step 4: 保存 & 通知
        task_manager.set_step(4, "レポート保存 & 通知処理", 85)
        saved_file = save_markdown_report(report)
        rep_id = os.path.splitext(os.path.basename(saved_file))[0]
        task_manager.add_log(f"レポートを保存しました: {saved_file}", "INFO")

        if dry_run:
            task_manager.add_log("Dry-run モードのため、メール/チャット送信はスキップしました。", "INFO")
        else:
            channel = notif_cfg.get("channel", "gmail").lower()
            if channel == "gmail":
                gmail_user = os.getenv("GMAIL_USER", "")
                gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
                gmail_cfg = notif_cfg.get("gmail", {})
                to_email = gmail_cfg.get("to_email", "") or gmail_user
                if gmail_user and gmail_password:
                    task_manager.add_log(f"Gmail送信中... ({to_email})", "INFO")
                    ok = send_via_gmail(report, gmail_user, gmail_password, to_email)
                    if ok:
                        task_manager.add_log("Gmail通知の送信に成功しました！", "INFO")
                    else:
                        task_manager.add_log("Gmail通知の送信でエラーが発生しました。", "WARNING")
                else:
                    task_manager.add_log("Gmail認証情報が未設定のためメール送信はスキップしました。", "INFO")
            elif channel == "none":
                task_manager.add_log("通知チャンネルが 'none' のため送信をスキップしました。", "INFO")
            else:
                task_manager.add_log(f"通知チャンネル '{channel}' に設定されています。", "INFO")

        with task_manager.lock:
            task_manager.status = "completed"
            task_manager.progress = 100
            task_manager.report_id = rep_id
            task_manager.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        task_manager.add_log("すべての処理が正常に完了しました！", "INFO")

    except Exception as e:
        logger.exception("レポート生成中にエラーが発生しました")
        with task_manager.lock:
            task_manager.status = "error"
            task_manager.error = str(e)
            task_manager.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_manager.add_log(f"エラー発生: {str(e)}", "ERROR")


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """REST API と静的アセットを配信するHTTPリクエストハンドラ"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _send_json(self, data: dict, status_code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        post_body = self.rfile.read(content_len).decode("utf-8")
        return json.loads(post_body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: システムステータス
        if path == "/api/status":
            load_dotenv(override=True)
            api_key = os.getenv("GEMINI_API_KEY", "")
            gmail_user = os.getenv("GMAIL_USER", "")
            gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
            reports = list_saved_reports()
            latest_id = reports[0]["id"] if reports else None

            config = load_config_dict()
            active_id = profile_manager.get_active_profile_id()
            active_prof = profile_manager.get_profile(active_id) or {}

            data = {
                "gemini_api_key_configured": bool(api_key and api_key != "your_gemini_api_key_here"),
                "gmail_configured": bool(gmail_user and gmail_pass),
                "channel": config.get("notification", {}).get("channel", "gmail"),
                "to_email": config.get("notification", {}).get("gmail", {}).get("to_email", ""),
                "reports_count": len(reports),
                "latest_report_id": latest_id,
                "current_kpi": active_prof.get("current_challenges", {}).get("focus_kpi") or config.get("company", {}).get("current_challenges", {}).get("focus_kpi", ""),
                "active_profile_id": active_id,
                "active_profile_name": active_prof.get("name", "自社")
            }
            return self._send_json(data)

        # API: プロファイル一覧
        elif path == "/api/profiles":
            profiles = profile_manager.list_profiles()
            active_id = profile_manager.get_active_profile_id()
            return self._send_json({"profiles": profiles, "active_profile_id": active_id})

        # API: 特定プロファイル詳細
        elif path.startswith("/api/profiles/"):
            pid = path.replace("/api/profiles/", "").strip()
            prof = profile_manager.get_profile(pid)
            if prof:
                return self._send_json(prof)
            return self._send_json({"error": "Profile not found"}, 404)

        # API: 設定取得
        elif path == "/api/config":
            config = load_config_dict()
            if config:
                return self._send_json(config)
            return self._send_json({"error": "config.yaml not found"}, 404)

        # API: レポート一覧
        elif path == "/api/reports":
            reports = list_saved_reports()
            return self._send_json({"reports": reports})

        # API: レポート詳細
        elif path.startswith("/api/reports/"):
            rep_id = path.replace("/api/reports/", "").strip()
            data = load_report_data(rep_id)
            if not data.get("raw_markdown") and not data.get("ideas"):
                return self._send_json({"error": "Report not found"}, 404)
            return self._send_json(data)

        # API: タスクステータス
        elif path == "/api/task_status":
            return self._send_json(task_manager.to_dict())

        # ルートURLは index.html を配信
        elif path == "/" or path == "/index.html":
            self.path = "/index.html"
            return super().do_GET()

        # 静的ファイル配信
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: プロファイルの保存（新規作成 / 更新）
        if path == "/api/profiles":
            try:
                data = self._read_json_body()
                saved = profile_manager.save_profile(data)
                return self._send_json({"success": True, "message": "プロファイルを保存しました。", "profile": saved})
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, 500)

        # API: プロファイルのアクティブ化
        elif path.startswith("/api/profiles/") and path.endswith("/activate"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "profiles" and parts[3] == "activate":
                pid = parts[2]
                ok = profile_manager.set_active_profile_id(pid)
                if ok:
                    return self._send_json({"success": True, "message": f"プロファイル '{pid}' をアクティブにしました。"})
                return self._send_json({"error": "Profile not found"}, 404)

        # API: プロファイルの複製
        elif path.startswith("/api/profiles/") and path.endswith("/duplicate"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "profiles" and parts[3] == "duplicate":
                pid = parts[2]
                body = self._read_json_body()
                new_name = body.get("name")
                dup = profile_manager.duplicate_profile(pid, new_name)
                if dup:
                    return self._send_json({"success": True, "profile": dup})
                return self._send_json({"error": "Profile not found"}, 404)

        # API: 設定更新
        elif path == "/api/config":
            try:
                data = self._read_json_body()
                save_config_dict(data)
                return self._send_json({"success": True, "message": "設定を保存しました。"})
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, 500)

        # API: レポート生成開始
        elif path == "/api/generate":
            with task_manager.lock:
                if task_manager.status == "running":
                    return self._send_json({"error": "既にレポート生成タスクが実行中です。"}, 409)

            body = self._read_json_body()
            thread = threading.Thread(target=run_generation_task, args=(body,), daemon=True)
            thread.start()
            return self._send_json({"success": True, "message": "生成タスクを開始しました。"})

        # API: 参謀と壁打ちする (Strategic Advisory Chat)
        elif path == "/api/consult":
            try:
                body = self._read_json_body()
                idea = body.get("idea", {})
                profile_id = body.get("profile_id", "").strip()
                question = body.get("question", "").strip()
                chat_history = body.get("chat_history", [])

                if not question:
                    return self._send_json({"error": "質問内容（question）を入力してください。"}, 400)

                load_dotenv(override=True)
                api_key = os.getenv("GEMINI_API_KEY", "")
                if not api_key or api_key == "your_gemini_api_key_here":
                    return self._send_json({"error": "GEMINI_API_KEY が設定されていません。"}, 400)

                # 対象プロファイルの取得
                prof = profile_manager.get_profile(profile_id) if profile_id else None
                if not prof:
                    act_id = profile_manager.get_active_profile_id()
                    prof = profile_manager.get_profile(act_id) or {}

                config = load_config_dict()
                model_name = config.get("model", {}).get("name", "gemini-3.8-flash")

                from analyzer import consult_idea_with_advisor
                answer = consult_idea_with_advisor(
                    api_key=api_key,
                    model_name=model_name,
                    idea=idea,
                    profile=prof,
                    question=question,
                    chat_history=chat_history
                )
                return self._send_json({"success": True, "answer": answer})
            except Exception as e:
                logger.exception("壁打ちAPI実行時エラー")
                return self._send_json({"success": False, "error": str(e)}, 500)

        # API: 戦略問診ウィザード - 動的質問生成
        elif path == "/api/wizard/questions":
            try:
                body = self._read_json_body()
                name = body.get("name", "").strip()
                url = body.get("url", "").strip()
                notes = body.get("notes", "").strip()

                if not name:
                    return self._send_json({"error": "会社名または事業名（name）を入力してください。"}, 400)

                load_dotenv(override=True)
                api_key = os.getenv("GEMINI_API_KEY", "")
                if not api_key or api_key == "your_gemini_api_key_here":
                    return self._send_json({"error": "GEMINI_API_KEY が設定されていません。"}, 400)

                config = load_config_dict()
                model_name = config.get("model", {}).get("name", "gemini-3.8-flash")

                from profiler import generate_wizard_questions
                data = generate_wizard_questions(
                    api_key=api_key,
                    model_name=model_name,
                    name=name,
                    url=url,
                    notes=notes
                )
                return self._send_json({"success": True, "data": data})
            except Exception as e:
                logger.exception("問診質問生成エラー")
                return self._send_json({"success": False, "error": str(e)}, 500)

        # API: 戦略問診ウィザード - プロファイル合成
        elif path == "/api/wizard/synthesize":
            try:
                body = self._read_json_body()
                name = body.get("name", "").strip()
                url = body.get("url", "").strip()
                notes = body.get("notes", "").strip()
                answers = body.get("answers", [])

                if not name:
                    return self._send_json({"error": "会社名または事業名（name）を入力してください。"}, 400)

                load_dotenv(override=True)
                api_key = os.getenv("GEMINI_API_KEY", "")
                if not api_key or api_key == "your_gemini_api_key_here":
                    return self._send_json({"error": "GEMINI_API_KEY が設定されていません。"}, 400)

                config = load_config_dict()
                model_name = config.get("model", {}).get("name", "gemini-3.8-flash")

                from profiler import synthesize_wizard_profile
                synthesized = synthesize_wizard_profile(
                    api_key=api_key,
                    model_name=model_name,
                    name=name,
                    url=url,
                    notes=notes,
                    qa_list=answers
                )
                return self._send_json({"success": True, "profile": synthesized})
            except Exception as e:
                logger.exception("プロファイル合成エラー")
                return self._send_json({"success": False, "error": str(e)}, 500)

        # API: Gmail送信
        elif path == "/api/send_email":
            try:
                body = self._read_json_body()
                rep_id = body.get("report_id")
                override_to = body.get("to_email", "").strip()

                if not rep_id:
                    return self._send_json({"error": "report_id が必要です"}, 400)

                load_dotenv(override=True)
                gmail_user = os.getenv("GMAIL_USER", "")
                gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")

                if not gmail_user or not gmail_password:
                    return self._send_json({"error": ".env に GMAIL_USER と GMAIL_APP_PASSWORD が設定されていません。"}, 400)

                # レポートデータ読み込み
                rep_data = load_report_data(rep_id)
                if not rep_data:
                    return self._send_json({"error": "指定されたレポートが見つかりません。"}, 404)

                # WeeklyReport オブジェクトに復元（JSONがある場合）
                from models import WeeklyReport, BizDevIdea
                ideas = [BizDevIdea(**item) for item in rep_data.get("ideas", [])]
                report = WeeklyReport(
                    report_title=rep_data.get("report_title", "週次ビジネス成長レポート"),
                    generated_at=rep_data.get("generated_at", ""),
                    company_name=rep_data.get("company_name", ""),
                    focus_kpi=rep_data.get("focus_kpi"),
                    ideas=ideas,
                    overall_trend_comment=rep_data.get("overall_trend_comment", "")
                )

                to_email = override_to or gmail_user
                success = send_via_gmail(report, gmail_user, gmail_password, to_email)
                if success:
                    return self._send_json({"success": True, "message": f"{to_email} へメールを送信しました。"})
                else:
                    return self._send_json({"success": False, "error": "メール送信に失敗しました。"}, 500)
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, 500)

        else:
            return self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        """DELETE リクエスト処理（プロファイル削除など）"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/profiles/"):
            pid = path.replace("/api/profiles/", "").strip()
            try:
                ok = profile_manager.delete_profile(pid)
                if ok:
                    return self._send_json({"success": True, "message": f"プロファイル '{pid}' を削除しました。"})
                return self._send_json({"error": "Profile not found"}, 404)
            except ValueError as ve:
                return self._send_json({"success": False, "error": str(ve)}, 400)
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, 500)
        else:
            return self._send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        """CORS プリフライト対応"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # 開発コンソールへの過度なログ出力を抑制（API呼び出しのみデバッグ）
        pass


def start_server(port: int = 8000, open_browser: bool = True):
    """Web UIサーバーを起動する（マルチスレッド同時リクエスト対応）"""
    server_address = ("127.0.0.1", port)
    try:
        httpd = ServerClass(server_address, DashboardRequestHandler)
    except OSError as e:
        # 48: macOS, 98: Linux, 10048: Windows WSAEADDRINUSE
        if e.errno in (48, 98, 10048) or "address already in use" in str(e).lower():
            logger.warning(f"ポート {port} は既に使用されています。ポート {port + 1} で起動を試みます。")
            start_server(port + 1, open_browser)
            return
        raise

    url = f"http://localhost:{port}"
    print("\n" + "=" * 60)
    print("🚀 ビジネス成長AIエージェント Webダッシュボードが起動しました！")
    print(f"👉 ブラウザで以下のURLを開いてください: {url}")
    print("=" * 60 + "\n")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました。")
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ビジネス成長AIエージェント Webダッシュボード")
    parser.add_argument("--port", type=int, default=8000, help="サーバーの待受ポート (デフォルト: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="起動時にブラウザを自動で開かない")
    args = parser.parse_args()

    start_server(port=args.port, open_browser=not args.no_browser)
