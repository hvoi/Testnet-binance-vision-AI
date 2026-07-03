import logging
import json
import os
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AIService")

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL_NAME = "qwen2.5-coder-7b-instruct@q5_k_m"


def load_bot_config() -> tuple:
    """Safe configuration loading from config.json."""
    current_dir = os.path.dirname(os.path.abspath(__file__)) 
    config_path = os.path.join(current_dir, "config.json")
    
    base_url = DEFAULT_BASE_URL
    model_name = DEFAULT_MODEL_NAME
    
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                model_name = config.get("DEFAULT_MODEL", DEFAULT_MODEL_NAME) 
                
                server_conn = config.get("LOCAL_SERVER_CONNECTION", {})
                host = server_conn.get("HOST", "localhost")
                port = server_conn.get("PORT", 1234)
                base_url = f"http://{host}:{port}/v1"
                logger.info(f"Configuration successfully loaded from {config_path}. Model: {model_name}")
        else: 
            logger.warning(f"Configuration file not found at: {config_path}. Using defaults.")
    except Exception as e:
        logger.error(f"Error parsing config.json: {e}. Using defaults.")
        
    return base_url, model_name 


BASE_URL, MODEL_NAME = load_bot_config()


async def evaluate_sentiment(
    prompt: str,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    return_raw: bool = False
) -> str:
    """Evaluate market sentiment using LLM."""
    api_key = os.getenv("GEMINI_API_KEY")
    
    if api_key and api_key != "AIzaSyYourActualKeyGoesHere":
        if base_url is None:
            base_url = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        if model_name is None:
            model_name = os.getenv("AI_MODEL_NAME", "gemini-2.5-flash")
    else:
        if base_url is None:
            base_url = BASE_URL
        if model_name is None:
            model_name = MODEL_NAME

    url = base_url
    if not url.endswith("/chat/completions") and not url.endswith("/chat/completions/"):
        if url.endswith("/"):
            url = f"{url}chat/completions"
        else:
            url = f"{url}/chat/completions"

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system", 
                "content": "You are a professional crypto fund AI analyst. Your task is to strictly follow user instructions and return responses exclusively in valid JSON format without any extra text."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1  
    }
    
    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "AIzaSyYourActualKeyGoesHere":
        headers["Authorization"] = f"Bearer {api_key}"
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"].strip()

            logger.info(json.dumps({
                "event": "ai_success",
                "model": model_name,
                "verdict": raw_content
            }, ensure_ascii=False))
            
            if return_raw:
                return raw_content
                
            verdict = raw_content.upper()
            if "POSITIVE" in verdict or "ПОЗИТИВ" in verdict:
                return "EXCLUSIVE_POSITIVE"
            elif "NEGATIVE" in verdict or "НЕГАТИВ" in verdict:
                return "EXCLUSIVE_NEGATIVE"
            else:
                return "NEUTRAL"
                
        except httpx.HTTPStatusError as exc:
            logger.error(json.dumps({
                "event": "ai_http_error",
                "status_code": exc.response.status_code,
                "error": str(exc)
            }))
            return "NEUTRAL"
            
        except httpx.RequestError as exc:
            logger.error(json.dumps({
                "event": "ai_network_error",
                "error": f"Connection error with AI server: {exc}"
            }))
            return "NEUTRAL"
            
        except Exception as exc:
            logger.error(json.dumps({
                "event": "ai_unexpected_error",
                "error": str(exc)
            }))
            return "NEUTRAL"