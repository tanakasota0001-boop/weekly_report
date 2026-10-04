import time
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# 安定して動作するフォールバックモデル一覧
CANDIDATE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]


def generate_with_fallback(
    client: genai.Client,
    preferred_model: str,
    contents: str,
    config: types.GenerateContentConfig,
    max_retries_per_model: int = 2
):
    """
    一時的な503混雑エラーやモデル利用不可に対応するため、
    リトライおよび代替モデルへの自動フォールバックを行う
    """
    models_to_try = [preferred_model] + [m for m in CANDIDATE_MODELS if m != preferred_model]

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
                # 503混雑や429レート制限の場合は少し待ってリトライ
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    logger.warning(f"モデル {model_name} が混雑しています (503/429)。2秒後に再試行します...")
                    time.sleep(2)
                else:
                    logger.warning(f"モデル {model_name} でエラーが発生しました: {e}。次のモデル候補に切り替えます。")
                    break

    logger.error("すべてのモデル候補で生成に失敗しました。")
    raise last_error
