#!/usr/bin/env python3
"""
Cron job to send meal reminders (breakfast, lunch, snacks, dinner) to users.

This script:
1. Fetches active users from the database (with metadata for chat_id)
2. For each user: fetches their active meal plan and current_date meal_plan_details
3. For each meal type present (breakfast, lunch, snacks, dinner):
   - Builds English reminder text
   - Translates to Hindi using translation_service (target language: Hindi)
   - Converts Hindi text to Hindi speech using ElevenLabs TTS
   - Saves the voice note to voice_mp3s
   - Sends text (English + Hindi) and voice note to WhatsApp via Periskope API
     using chat_id from metadata.whatsapp_group_metadata.group_metadata.id

Run as a cron job, e.g.:
    # Breakfast reminder at 7 AM, lunch at 12 PM, snacks at 4 PM, dinner at 8 PM
    0 7 * * * cd /path/to/foodeasy-backend && python3 cron_jobs/send_meal_reminders.py

Environment Variables:
    - GOOGLE_CLOUD_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_JSON: For translation
    - GOOGLE_CLOUD_PROJECT: Google Cloud project ID
    - ELEVEN_LABS_API_KEY, ELEVEN_LABS_VOICE_ID: For TTS (Hindi speech)
    - PERISKOPE_PHONE_NUMBER, PERISKOPE_API_TOKEN, PERISKOPE_API_BASE_URL: For WhatsApp
    - SLACK_WEBHOOK_URL: (Optional) Slack Incoming Webhook for delivery/failure alerts
    - VOICE_MP3S_DIR: (Optional) Directory for saved MP3s; defaults to voice_mp3s/
"""

import sys
import os
import base64
from datetime import datetime, date
from typing import List, Dict, Any, Optional

import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.supabase_client import get_supabase_admin
from app.services.meal_messaging_service import meal_messaging_service
from app.services.translation_service import translation_service
from app.services.elevenlabs_tts_service import (
    ElevenLabsTTSService,
    save_audio_to_voice_dir,
)

# Target language for translation: always Hindi
TARGET_LANGUAGE = "hi"
MEAL_TYPES_ORDER = ["breakfast", "lunch", "snacks", "dinner"]


def get_chat_id_from_metadata(metadata: Any) -> Optional[str]:
    """
    Get WhatsApp chat_id from user_profiles.metadata.
    Prefers metadata.whatsapp_group_metadata.group_metadata.id, then fallbacks.
    """
    if not metadata or not isinstance(metadata, dict):
        return None
    wgm = metadata.get("whatsapp_group_metadata") or {}
    if not isinstance(wgm, dict):
        return None
    group_metadata = wgm.get("group_metadata") or {}
    if isinstance(group_metadata, dict):
        chat_id = group_metadata.get("id")
        if chat_id:
            return chat_id
    return wgm.get("chat_id") or wgm.get("id") or metadata.get("chat_id")


def get_active_users() -> List[Dict[str, Any]]:
    """
    Fetch all active users from user_profiles with metadata (for chat_id).

    Returns:
        List of dicts with "id" (user_id) and "metadata".
    """
    supabase = get_supabase_admin()
    try:
        response = supabase.table("user_profiles").select("id, metadata").eq(
            "is_active", True
        ).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching active users: {str(e)}")
        raise


def _periskope_send_url() -> str:
    """Base URL for Periskope API (doc: https://docs.periskope.app/api-reference/message/send-message)."""
    base = os.getenv("PERISKOPE_API_BASE_URL", "https://api.periskope.app/v1").rstrip("/")
    if "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/message/send"


async def send_whatsapp_message(chat_id: str, message: str) -> bool:
    """Send a text message via Periskope API (POST /message/send, chat_id + message)."""
    try:
        periskope_phone = os.getenv("PERISKOPE_PHONE_NUMBER")
        periskope_token = os.getenv("PERISKOPE_API_TOKEN")
        if not periskope_phone or not periskope_token:
            print("PERISKOPE_PHONE_NUMBER or PERISKOPE_API_TOKEN not set")
            return False
        url = _periskope_send_url()
        headers = {
            "x-phone": periskope_phone,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {periskope_token}",
        }
        payload = {"chat_id": chat_id, "message": message}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return True
            print(f"Periskope send message failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return False


async def send_whatsapp_audio(chat_id: str, audio_path: str) -> bool:
    """Send an audio file (voice note) via Periskope API.
    Media object: type=audio, filedata=base64, filename, mimetype (see send-message doc).
    """
    try:
        periskope_phone = os.getenv("PERISKOPE_PHONE_NUMBER")
        periskope_token = os.getenv("PERISKOPE_API_TOKEN")
        if not periskope_phone or not periskope_token:
            return False
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        filedata_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        filename = os.path.basename(audio_path) or "voice_note.mp3"
        url = _periskope_send_url()
        headers = {
            "x-phone": periskope_phone,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {periskope_token}",
        }
        payload = {
            "chat_id": chat_id,
            "media": {
                "type": "audio",
                "filedata": filedata_b64,
                "filename": filename,
                "mimetype": "audio/mpeg",
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return True
            print(f"Periskope send audio failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Error sending WhatsApp audio: {e}")
        return False


async def send_slack_alert(message: str) -> bool:
    """Send a single message to Slack via Incoming Webhook."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not set, skipping Slack alert")
        return False
    try:
        payload = {"text": f"```\n{message}\n```"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                print("Slack alert sent successfully")
                return True
            print(f"Failed to send Slack alert: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Slack alert: {e}")
        return False


def _build_slack_message(summary: Dict[str, Any]) -> str:
    """Build a compiled Slack message for success/failure alerts from run results."""
    lines = [
        "*Meal Reminders Cron – Completed*",
        f"Run: {summary.get('timestamp', '')}",
        f"Date: {summary.get('date', '')}",
        f"Users processed: {summary.get('users_processed', 0)}",
        f"Reminders generated: {summary.get('reminders_generated', 0)}",
    ]
    results = summary.get("results") or []
    sent_text_count = sum(1 for r in results if r.get("sent_text"))
    sent_audio_count = sum(1 for r in results if r.get("sent_audio"))
    lines.append(f"*Successful delivery:* {sent_text_count} text, {sent_audio_count} audio")
    failures = [r for r in results if r.get("error") or not r.get("sent_text")]
    if failures:
        lines.append("")
        lines.append("*Failures / partial:*")
        for r in failures[:20]:  # cap at 20
            uid = r.get("user_id", "?")
            meal = r.get("meal_type") or "user_error"
            err = r.get("error") or ("text not sent" if not r.get("sent_text") else "")
            lines.append(f"• user {uid} | {meal} | {err}")
        if len(failures) > 20:
            lines.append(f"… and {len(failures) - 20} more")
    else:
        lines.append("No failures.")
    return "\n".join(lines)


async def process_user_meal_reminders(
    user_id: str,
    target_date: date,
    tts_service: ElevenLabsTTSService,
    chat_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    For one user, get today's meal plan by type; for each meal type present,
    translate English message to Hindi and generate Hindi speech, save audio,
    and send text + voice note to WhatsApp via Periskope if chat_id is set.

    Returns:
        List of dicts: {meal_type, english_text, hindi_text, audio_path, sent_text?, sent_audio?, error?}
    """
    results = []
    user_id_str = str(user_id) if user_id is not None else ""
    meals_by_type = await meal_messaging_service._get_today_meal_plan(
        user_id_str, target_date
    )
    if not meals_by_type:
        return results

    date_str = target_date.isoformat()
    user_short = (user_id_str or "unknown")[:8]

    for meal_type in MEAL_TYPES_ORDER:
        if meal_type not in meals_by_type:
            continue
        items = meals_by_type[meal_type]
        english_text = meal_messaging_service._format_meal_message(
            meal_type, items
        )
        if not english_text:
            continue

        # Translate English -> Hindi
        try:
            trans_result = await translation_service.translate_async(
                english_text, target_language=TARGET_LANGUAGE, source_language="en"
            )
            hindi_text = trans_result.translated or english_text
        except Exception as e:
            print(f"Translation failed for user {user_id} {meal_type}: {e}")
            results.append({
                "meal_type": meal_type,
                "english_text": english_text,
                "hindi_text": None,
                "audio_path": None,
                "error": f"translation: {e}",
            })
            continue

        # Build recipe lines: Recipe (रेसिपी): Name (Hindi name) url
        recipe_lines = []
        for item in items:
            recipe_link = item.get("recipe_link") if isinstance(item, dict) else None
            if not recipe_link:
                continue
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            if not name:
                continue
            try:
                item_trans = await translation_service.translate_async(
                    name, target_language=TARGET_LANGUAGE, source_language="en"
                )
                hindi_name = (item_trans.translated or name).strip()
            except Exception:
                hindi_name = name
            recipe_lines.append(f"Recipe (रेसिपी): {name} ({hindi_name}) {recipe_link}")

        # Hindi text -> Hindi speech via ElevenLabs
        audio_path = None
        err = None
        if tts_service.is_configured:
            try:
                audio_bytes = await tts_service.text_to_speech(hindi_text)
                if audio_bytes:
                    filename = f"reminder_{date_str}_{user_short}_{meal_type}.mp3"
                    path = save_audio_to_voice_dir(audio_bytes, filename)
                    if path:
                        audio_path = str(path)
            except Exception as e:
                err = f"tts: {e}"
                print(f"TTS failed for user {user_id} {meal_type}: {e}")
        else:
            err = "TTS not configured (ELEVEN_LABS_API_KEY / ELEVEN_LABS_VOICE_ID)"

        sent_text = False
        sent_audio = False
        if chat_id:
            combined_message = f"{english_text}\n\n{hindi_text}"
            if recipe_lines:
                combined_message += "\n\n" + "\n".join(recipe_lines)
            sent_text = await send_whatsapp_message(chat_id, combined_message)
            if audio_path:
                sent_audio = await send_whatsapp_audio(chat_id, audio_path)

        results.append({
            "meal_type": meal_type,
            "english_text": english_text,
            "hindi_text": hindi_text,
            "audio_path": audio_path,
            "sent_text": sent_text,
            "sent_audio": sent_audio,
            "error": err,
        })

    return results


async def run_meal_reminders(
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Main flow: active users -> active meal plan for today -> for each meal type
    present: translate to Hindi, TTS Hindi, save audio, send text + voice via Periskope.
    """
    if target_date is None:
        target_date = date.today()

    print(f"[{datetime.now().isoformat()}] Starting meal reminders for {target_date.isoformat()}")

    try:
        users = get_active_users()
        print(f"Found {len(users)} active users")

        tts_service = ElevenLabsTTSService()
        if not tts_service.is_configured:
            print("Warning: ElevenLabs TTS not configured; voice files will not be generated")

        all_results = []
        for u in users:
            user_id = u.get("id")
            if not user_id:
                continue
            chat_id = get_chat_id_from_metadata(u.get("metadata"))
            if not chat_id:
                print(f"No chat_id for user {user_id}, skipping WhatsApp send")
            try:
                per_user = await process_user_meal_reminders(
                    user_id, target_date, tts_service, chat_id=chat_id
                )
                for r in per_user:
                    all_results.append({"user_id": user_id, **r})
            except Exception as e:
                print(f"Error processing user {user_id}: {e}")
                all_results.append({
                    "user_id": user_id,
                    "meal_type": None,
                    "english_text": None,
                    "hindi_text": None,
                    "audio_path": None,
                    "sent_text": False,
                    "sent_audio": False,
                    "error": str(e),
                })

        summary = {
            "success": True,
            "date": target_date.isoformat(),
            "users_processed": len(users),
            "reminders_generated": len(all_results),
            "results": all_results,
            "timestamp": datetime.now().isoformat(),
        }
        print(f"Processed {len(users)} users, {len(all_results)} reminders")
        slack_msg = _build_slack_message(summary)
        await send_slack_alert(slack_msg)
        return summary

    except Exception as e:
        print(f"Error in meal reminders cron: {e}")
        import traceback
        traceback.print_exc()
        failure_msg = (
            "*Meal Reminders Cron – Failed*\n"
            f"Run: {datetime.now().isoformat()}\n"
            f"Date: {target_date.isoformat()}\n"
            f"Error: {e}"
        )
        await send_slack_alert(failure_msg)
        return {
            "success": False,
            "error": str(e),
            "date": target_date.isoformat(),
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    result = asyncio.run(run_meal_reminders())
    sys.exit(0 if result.get("success", False) else 1)
