#!/usr/bin/env python3
"""
Simple test for the ElevenLabs text-to-speech service.
Requires ELEVEN_LABS_API_KEY and ELEVEN_LABS_VOICE_ID in .env.

Usage (from project root):
  python -m scripts.test_tts
  python -m scripts.test_tts "Custom text to speak"
"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, ".")


async def main():
    from app.services.elevenlabs_tts_service import (
        ElevenLabsTTSService,
        save_audio_to_voice_dir,
    )

    text = sys.argv[1].strip() if len(sys.argv) > 1 else "आज नाश्ते में मूंग दाल चीला है।"
    svc = ElevenLabsTTSService()

    if not svc.is_configured:
        print("ERROR: TTS not configured. Set ELEVEN_LABS_API_KEY and ELEVEN_LABS_VOICE_ID in .env")
        sys.exit(1)

    print(f"Converting to speech: {text[:60]}{'...' if len(text) > 60 else ''}")
    audio_bytes = await svc.text_to_speech(text)
    if audio_bytes is None:
        print("ERROR: Failed to generate speech.")
        sys.exit(1)

    print(f"Generated {len(audio_bytes)} bytes of audio.")
    filename = f"test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp3"
    path = save_audio_to_voice_dir(audio_bytes, filename)
    if path:
        print(f"Saved to: {path}")
    else:
        print("Warning: could not save to voice_mp3s (audio bytes still returned).")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
