import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key and api_key != "AIzaSyYourActualKeyGoesHere":
    API_URL = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    MODEL_NAME = os.getenv("AI_MODEL_NAME", "gemini-2.5-flash")
else:
    API_URL = "http://127.0.0.1:1234/v1/chat/completions"
    MODEL_NAME = "qwen2.5-coder-7b-instruct@q5_k_m"

test_news = "Bitcoin price surges by 10% after unexpected interest rate cut by the Federal Reserve."


def test_ai_connection():
    news_text = test_news
    print(f"Sending request to LLM: '{news_text}'\n")

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "You are a professional AI analyst. Return the answer in JSON: {\"verdict\": \"EXCLUSIVE_POSITIVE/EXCLUSIVE_NEGATIVE/NEUTRAL\", \"importance\": 1-5}."
            },
            {
                "role": "user",
                "content": f"Analyze news: {news_text}"
            }
        ],
        "temperature": 0.1
    }

    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "AIzaSyYourActualKeyGoesHere":
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.post(API_URL, json=payload, headers=headers, timeout=60.0)
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print("[OK] Response from LLM:")
            print(content)
        else:
            print(f"[ERROR] Server error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"[ERROR] Failed to connect to LLM: {e}")


if __name__ == "__main__":
    test_ai_connection()
