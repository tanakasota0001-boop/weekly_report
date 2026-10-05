import time
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# 安定して動作する現行の最新フォールバックモデル一覧
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite"
]


def generate_with_fallback(
    client: genai.Client,
    preferred_model: str,
    contents: str,
    config: types.GenerateContentConfig,
    max_retries_per_model: int = 2
):
    """
    一時的な503混雑エラー、429レート制限、またはモデル非推奨・404に対応するため、
    リトライおよび最新代替モデルへの自動フォールバックを行う
    """
    # preferred_model を先頭に、CANDIDATE_MODELS から重複を除いて順序付け
    models_to_try = [preferred_model]
    for m in CANDIDATE_MODELS:
        if m != preferred_model and m not in models_to_try:
            models_to_try.append(m)

    last_error = None
    for model_name in models_to_try:
        for attempt in range(max_retries_per_model):
            try:
                logger.info(f"LLM呼び出し試行中: {model_name} (試行 {attempt + 1}/{max_retries_per_model})")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                err_str = str(e)
                last_error = e

                # 404 NOT_FOUND（モデル廃止・非推奨）の場合はリトライせず即座に次のモデル候補へ
                if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str:
                    logger.warning(f"モデル {model_name} は利用不可（404/廃止）です。最新の代替モデル候補に切り替えます。")
                    break

                # 503混雑や429レート制限の場合は待機してリトライ
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_sec = 2 * (attempt + 1)
                    logger.warning(f"モデル {model_name} が混雑またはレート制限です (503/429)。{wait_sec}秒待機して再試行します...")
                    time.sleep(wait_sec)
                else:
                    logger.warning(f"モデル {model_name} でエラーが発生しました: {e}。次のモデル候補に切り替えます。")
                    break

    logger.error("すべてのモデル候補で生成に失敗しました。")
    raise last_error
