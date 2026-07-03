import asyncio
from ai_service import evaluate_sentiment


async def main():
    news_cases = [
        {
            "news": "MicroStrategy acquires an additional 15,000 BTC for $1.2B, boosting institutional treasury reserves.",
            "expected_sentiment": "EXCLUSIVE_POSITIVE"
        },
        {
            "news": "US SEC launches urgent investigation into top DeFi protocols, sparking massive regulatory panic and asset sell-off.",
            "expected_sentiment": "EXCLUSIVE_NEGATIVE"
        },
        {
            "news": "Bitcoin funding rates and daily trading volume stabilize over the weekend ahead of upcoming macro data release.",
            "expected_sentiment": "NEUTRAL"
        }
    ]

    print("🚀 Starting AI analyst calibration...")
    print("=" * 80)

    for case in news_cases:
        sentiment = await evaluate_sentiment(case["news"])
        
        print(f"📰 News: {case['news']}")
        print(f"🎯 Expected verdict: {case['expected_sentiment']}")
        print(f"🧠 Actual verdict: {sentiment}")
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())