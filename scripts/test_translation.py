#!/usr/bin/env python3
"""
Simple test for the translation service.
Uses Google Cloud Translation v3 if configured; otherwise falls back to googletrans.

Usage (from project root):
  python -m scripts.test_translation
  python -m scripts.test_translation "Hello, how are you?"
  python -m scripts.test_translation "नमस्ते" hi
"""
import asyncio
import sys

sys.path.insert(0, ".")


def main():
    from app.services.translation_service import TranslationService

    svc = TranslationService()

    # Default: translate a Hindi phrase to English, and English to Hindi
    if len(sys.argv) >= 2:
        text = sys.argv[1].strip()
        target = sys.argv[2].strip() if len(sys.argv) >= 3 else "en"
    else:
        text = "Today's breakfast is Moong Dal Cheela."
        target = "hi"

    print(f"Input:  {text}")
    print(f"Target: {target}")
    print("-" * 50)

    result = svc.translate(text, target_language=target)
    print(f"Original:   {result.original}")
    print(f"Translated: {result.translated}")
    print(f"Source lang: {result.source_language}")
    print("-" * 50)

    # Quick async test
    async def run_async():
        r = await svc.translate_async("Good morning", target_language="hi")
        print("Async test (Good morning -> hi):", r.translated)

    asyncio.run(run_async())
    print("Done.")


if __name__ == "__main__":
    main()
