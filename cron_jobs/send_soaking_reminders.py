#!/usr/bin/env python3
"""
Cron job to send soaking reminders to users (shared logic for both jobs).

For meals that have ingredients requiring soaking (meal_item_ingredients.is_soaking_item = true),
sends English + Hindi text and voice note via WhatsApp (same pattern as meal reminders).

Single command (Railway server is UTC; send times are IST):
   Schedule at 5am IST and 5pm IST using UTC cron. The script uses IST to pick the job:
   - 5am IST (23:30 UTC previous day): today's dinner soaking reminders.
   - 5pm IST (11:30 UTC same day): tomorrow's breakfast, lunch, snacks soaking reminders.

   Command:  python cron_jobs/send_soaking_reminders.py
   Cron:     30 23 * * *  and  30 11 * * *

   Optional: pass tomorrow_meals or today_dinner to force a mode; or set SOAKING_FOR env.

Environment Variables: same as send_meal_reminders (translation, TTS, Periskope, Slack, VOICE_MP3S_DIR).

When text/voice send fails, the Slack alert and result "error" field show the reason, e.g.:
   - No chat_id: user_profiles.metadata missing whatsapp_group_metadata.group_metadata.id
   - Periskope: env PERISKOPE_PHONE_NUMBER / PERISKOPE_API_TOKEN wrong or API returned 4xx/5xx (see response in error)
   - TTS not configured: ELEVEN_LABS_API_KEY / ELEVEN_LABS_VOICE_ID not set (voice not sent; text may still send)
"""

import sys
import os
import base64
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except ImportError:
    # Python < 3.9: use fixed UTC+5:30 for IST
    IST = timezone(timedelta(hours=5, minutes=30))

import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.supabase_client import get_supabase_admin
from app.services.translation_service import translation_service
from app.services.elevenlabs_tts_service import (
    ElevenLabsTTSService,
    save_audio_to_voice_dir,
)

TARGET_LANGUAGE = "hi"

SOAKING_FOR_TODAY_DINNER = "today_dinner"
SOAKING_FOR_TOMORROW_MEALS = "tomorrow_meals"


def get_chat_id_from_metadata(metadata: Any) -> Optional[str]:
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
    supabase = get_supabase_admin()
    try:
        response = supabase.table("user_profiles").select("id, metadata").eq(
            "is_active", True
        ).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching active users: {str(e)}")
        raise


def get_soaking_items_for_date(
    user_id: str,
    target_date: date,
    meal_types_filter: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Meal items with soaking ingredients (meal_item_ingredients.is_soaking_item = true)."""
    supabase = get_supabase_admin()
    date_str = target_date.isoformat()
    user_id_str = str(user_id)

    plan_resp = supabase.table("user_meal_plan").select("id").eq("user_id", user_id_str).eq(
        "is_active", True
    ).lte("start_date", date_str).gte("end_date", date_str).order("id", desc=True).limit(1).execute()
    if not plan_resp.data:
        return {}
    user_meal_plan_id = plan_resp.data[0]["id"]

    details_resp = supabase.table("user_meal_plan_details").select(
        "meal_type_id, meal_item_id, meal_types (id, name), meal_items (id, name)"
    ).eq("user_meal_plan_id", user_meal_plan_id).eq("date", date_str).eq("is_active", True).order(
        "meal_type_id"
    ).execute()

    item_to_meal: Dict[int, tuple] = {}
    for detail in details_resp.data or []:
        mt = detail.get("meal_types")
        mi = detail.get("meal_items")
        meal_item_id = detail.get("meal_item_id")
        if not mt or not mi or not meal_item_id:
            continue
        mt = mt[0] if isinstance(mt, list) else mt
        mi = mi[0] if isinstance(mi, list) else mi
        meal_type_name = (mt.get("name") or "").lower()
        meal_item_name = mi.get("name") or ""
        if meal_type_name and meal_item_name:
            if meal_types_filter and meal_type_name not in meal_types_filter:
                continue
            item_to_meal[meal_item_id] = (meal_type_name, meal_item_name)
    if not item_to_meal:
        return {}

    ing_resp = supabase.table("meal_item_ingredients").select(
        "meal_item_id, meal_ingredients (name)"
    ).in_("meal_item_id", list(item_to_meal.keys())).eq("is_active", True).eq(
        "is_soaking_item", True
    ).execute()

    soak_by_item: Dict[int, List[str]] = {}
    for row in ing_resp.data or []:
        meal_item_id = row.get("meal_item_id")
        ing = row.get("meal_ingredients")
        if not meal_item_id:
            continue
        if ing:
            ing = ing[0] if isinstance(ing, list) else ing
            name = ing.get("name") if isinstance(ing, dict) else None
            if name:
                soak_by_item.setdefault(meal_item_id, []).append(name)

    result: Dict[str, List[Dict[str, Any]]] = {}
    for meal_item_id, soak_ingredients in soak_by_item.items():
        if not soak_ingredients:
            continue
        tup = item_to_meal.get(meal_item_id)
        if not tup:
            continue
        meal_type_name, meal_item_name = tup
        if meal_type_name not in result:
            result[meal_type_name] = []
        result[meal_type_name].append({"meal_name": meal_item_name, "soak_ingredients": soak_ingredients})
    return result


def format_soaking_messages(
    soaking_by_type: Dict[str, List[Dict[str, Any]]],
    for_tomorrow: bool,
) -> List[str]:
    messages = []
    for meal_type, entries in soaking_by_type.items():
        meal_type_cap = meal_type.capitalize()
        prefix = "Tomorrow's" if for_tomorrow else "Today's"
        for entry in entries:
            meal_name = entry.get("meal_name", "")
            soak_list = entry.get("soak_ingredients") or []
            if not meal_name or not soak_list:
                continue
            soak_text = soak_list[0] if len(soak_list) == 1 else ", ".join(soak_list[:-1]) + f" and {soak_list[-1]}"
            messages.append(f"{prefix} {meal_type_cap} contains {meal_name}. Soak {soak_text}.")
    return messages


def _periskope_send_url() -> str:
    base = os.getenv("PERISKOPE_API_BASE_URL", "https://api.periskope.app/v1").rstrip("/")
    if "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/message/send"


async def send_whatsapp_message(chat_id: str, message: str) -> Tuple[bool, Optional[str]]:
    """Returns (success, error_detail). error_detail is None on success."""
    try:
        periskope_phone = os.getenv("PERISKOPE_PHONE_NUMBER")
        periskope_token = os.getenv("PERISKOPE_API_TOKEN")
        if not periskope_phone or not periskope_token:
            msg = "PERISKOPE_PHONE_NUMBER or PERISKOPE_API_TOKEN not set"
            print(msg)
            return False, msg
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
                return True, None
            detail = f"Periskope text: {response.status_code} {response.text}"
            print(detail)
            return False, detail
    except Exception as e:
        detail = f"WhatsApp text error: {e}"
        print(detail)
        return False, detail


async def send_whatsapp_audio(chat_id: str, audio_path: str) -> Tuple[bool, Optional[str]]:
    """Returns (success, error_detail). error_detail is None on success."""
    try:
        periskope_phone = os.getenv("PERISKOPE_PHONE_NUMBER")
        periskope_token = os.getenv("PERISKOPE_API_TOKEN")
        if not periskope_phone or not periskope_token:
            return False, "PERISKOPE_PHONE_NUMBER or PERISKOPE_API_TOKEN not set"
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
                return True, None
            detail = f"Periskope audio: {response.status_code} {response.text}"
            print(detail)
            return False, detail
    except FileNotFoundError as e:
        detail = f"Audio file not found: {e}"
        print(detail)
        return False, detail
    except Exception as e:
        detail = f"WhatsApp audio error: {e}"
        print(detail)
        return False, detail


async def send_slack_alert(message: str) -> bool:
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
    lines = [
        "*Soaking Reminders Cron – Completed*",
        f"Run: {summary.get('timestamp', '')}",
        f"Date: {summary.get('date', '')}",
        f"Soaking for: {summary.get('soaking_for', '')}",
        f"Users processed: {summary.get('users_processed', 0)}",
        f"Reminders generated: {summary.get('reminders_generated', 0)}",
    ]
    results = summary.get("results") or []
    sent_text_count = sum(1 for r in results if r.get("sent_text"))
    sent_audio_count = sum(1 for r in results if r.get("sent_audio"))
    lines.append(f"*Successful delivery:* {sent_text_count} text, {sent_audio_count} audio")

    # Description: list of reminders sent (user, meal_type, message)
    sent = [r for r in results if r.get("sent_text") and r.get("english_text")]
    if sent:
        lines.append("")
        lines.append("*Description (reminders sent):*")
        for r in sent[:30]:
            uid = r.get("user_id", "?")
            meal = r.get("meal_type") or "—"
            desc = (r.get("english_text") or "").strip()
            if len(desc) > 80:
                desc = desc[:77] + "..."
            lines.append(f"• user {uid} | {meal} | {desc}")
        if len(sent) > 30:
            lines.append(f"… and {len(sent) - 30} more")

    failures = [r for r in results if r.get("error") or not r.get("sent_text")]
    if failures:
        lines.append("")
        lines.append("*Failures / partial:*")
        for r in failures[:20]:
            uid = r.get("user_id", "?")
            meal = r.get("meal_type") or "user_error"
            err = r.get("error") or ("text not sent" if not r.get("sent_text") else "")
            lines.append(f"• user {uid} | {meal} | {err}")
        if len(failures) > 20:
            lines.append(f"… and {len(failures) - 20} more")
    else:
        lines.append("")
        lines.append("No failures.")
    return "\n".join(lines)


async def process_user_soaking_reminders(
    user_id: str,
    target_date: date,
    meal_types: List[str],
    for_tomorrow: bool,
    tts_service: ElevenLabsTTSService,
    chat_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results = []
    user_id_str = str(user_id) if user_id is not None else ""
    soaking_by_type = get_soaking_items_for_date(user_id_str, target_date, meal_types_filter=meal_types)
    if not soaking_by_type:
        print(f"User {user_id_str}: no soaking items for {target_date.isoformat()}")
        return results

    for meal_type, entries in soaking_by_type.items():
        for entry in entries:
            meal_name = entry.get("meal_name", "")
            soak_list = entry.get("soak_ingredients") or []
            if meal_name or soak_list:
                print(f"User {user_id_str}: {meal_type} – meal: {meal_name}, soak: {', '.join(soak_list)}")

    date_str = target_date.isoformat()
    user_short = (user_id_str or "unknown")[:8]
    messages = format_soaking_messages(soaking_by_type, for_tomorrow)
    if not messages:
        return results

    for idx, english_text in enumerate(messages):
        meal_type_label = "soaking"
        for mt in meal_types:
            if mt in soaking_by_type:
                meal_type_label = f"soaking_{mt}"
                break

        try:
            trans_result = await translation_service.translate_async(
                english_text, target_language=TARGET_LANGUAGE, source_language="en"
            )
            hindi_text = trans_result.translated or english_text
        except Exception as e:
            print(f"Soaking translation failed for user {user_id}: {e}")
            results.append({
                "meal_type": meal_type_label,
                "english_text": english_text,
                "hindi_text": None,
                "audio_path": None,
                "sent_text": False,
                "sent_audio": False,
                "error": f"translation: {e}",
            })
            continue

        audio_path = None
        err = None
        if tts_service.is_configured:
            try:
                audio_bytes = await tts_service.text_to_speech(hindi_text)
                if audio_bytes:
                    filename = f"soaking_{date_str}_{user_short}_{idx}.mp3"
                    path = save_audio_to_voice_dir(audio_bytes, filename)
                    if path:
                        audio_path = str(path)
            except Exception as e:
                err = f"tts: {e}"
                print(f"Soaking TTS failed for user {user_id}: {e}")
        else:
            err = "TTS not configured"

        sent_text = False
        sent_audio = False
        if not chat_id:
            err = err or "No chat_id (user metadata missing whatsapp_group_metadata)"
            print(f"User {user_id}: {err}")
        else:
            combined_message = f"{english_text}\n\n{hindi_text}"
            sent_text, text_err = await send_whatsapp_message(chat_id, combined_message)
            if not sent_text and text_err:
                err = err or text_err
            if audio_path:
                sent_audio, audio_err = await send_whatsapp_audio(chat_id, audio_path)
                if not sent_audio and audio_err:
                    err = err or audio_err or "WhatsApp audio send failed"
            if not sent_text and not err:
                err = "WhatsApp text send failed (check console for Periskope response)"

        results.append({
            "meal_type": meal_type_label,
            "english_text": english_text,
            "hindi_text": hindi_text,
            "audio_path": audio_path,
            "sent_text": sent_text,
            "sent_audio": sent_audio,
            "error": err,
        })

    return results


def _now_ist() -> datetime:
    """Current time in IST (Asia/Kolkata)."""
    return datetime.now(IST)


def _is_evening_ist() -> bool:
    """True if current IST time is noon or later (evening/afternoon). Used to avoid sending today's dinner reminder in the evening IST."""
    return _now_ist().hour >= 12


async def run_soaking_reminders(
    target_date: Optional[date] = None,
    soaking_for: str = SOAKING_FOR_TODAY_DINNER,
) -> Dict[str, Any]:
    """
    soaking_for: today_dinner = target_date dinner, "Today's ..."; tomorrow_meals = target_date+1 breakfast/lunch/snacks, "Tomorrow's ...".
    Today's dinner reminders are never sent in the evening IST (noon or later); the job exits without sending.
    """
    if target_date is None:
        target_date = date.today()

    s = soaking_for.strip().lower()
    if s == SOAKING_FOR_TOMORROW_MEALS:
        soaking_date = target_date + timedelta(days=1)
        soaking_meal_types = ["breakfast", "lunch", "snacks"]
        soaking_for_tomorrow = True
        print(f"[{datetime.now().isoformat()}] Soaking reminders for {soaking_date.isoformat()} (breakfast, lunch, snacks)")
    else:
        # Today's dinner: do not send in the evening IST. Intended for 5am IST only.
        if _is_evening_ist():
            print(f"[{datetime.now().isoformat()}] Skipping today's dinner soaking reminder (evening IST); run at 5am IST only.")
            return {
                "success": True,
                "date": target_date.isoformat(),
                "soaking_for": soaking_for,
                "users_processed": 0,
                "reminders_generated": 0,
                "results": [],
                "timestamp": datetime.now().isoformat(),
                "skipped": "evening_ist",
            }
        soaking_date = target_date
        soaking_meal_types = ["dinner"]
        soaking_for_tomorrow = False
        print(f"[{datetime.now().isoformat()}] Soaking reminders for {soaking_date.isoformat()} (dinner)")

    try:
        users = get_active_users()
        print(f"Found {len(users)} active users")

        tts_service = ElevenLabsTTSService()
        if not tts_service.is_configured:
            print("Warning: ElevenLabs TTS not configured; voice files will not be generated")

        all_results = []
        user_ids = [u.get("id") for u in users if u.get("id")]
        print(f"Active user ids: {user_ids}")
        for u in users:
            user_id = u.get("id")
            if not user_id:
                continue
            print(f"Processing user {user_id}")
            chat_id = get_chat_id_from_metadata(u.get("metadata"))
            if not chat_id:
                print(f"No chat_id for user {user_id}, skipping WhatsApp send")
            try:
                soaking_results = await process_user_soaking_reminders(
                    user_id, soaking_date, soaking_meal_types, soaking_for_tomorrow,
                    tts_service, chat_id=chat_id,
                )
                for r in soaking_results:
                    all_results.append({"user_id": user_id, **r})
            except Exception as e:
                print(f"Error processing user {user_id} soaking reminders: {e}")
                all_results.append({
                    "user_id": user_id,
                    "meal_type": "soaking",
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
            "soaking_for": soaking_for,
            "users_processed": len(users),
            "reminders_generated": len(all_results),
            "results": all_results,
            "timestamp": datetime.now().isoformat(),
        }
        print(f"Processed {len(users)} users, {len(all_results)} soaking reminders")
        slack_msg = _build_slack_message(summary)
        await send_slack_alert(slack_msg)
        return summary

    except Exception as e:
        print(f"Error in soaking reminders cron: {e}")
        import traceback
        traceback.print_exc()
        failure_msg = (
            "*Soaking Reminders Cron – Failed*\n"
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
    # Single command: no args → pick mode from IST (morning IST = today_dinner, evening IST = tomorrow_meals).
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower() or os.getenv("SOAKING_FOR", "")
    if not mode:
        mode = SOAKING_FOR_TOMORROW_MEALS if _is_evening_ist() else SOAKING_FOR_TODAY_DINNER
        now_ist = _now_ist()
        print(f"[{datetime.now().isoformat()}] Auto mode: {mode} (IST {now_ist.strftime('%H:%M')}, hour {'>= 12' if _is_evening_ist() else '< 12'})")
    if mode == SOAKING_FOR_TOMORROW_MEALS:
        soaking_for = SOAKING_FOR_TOMORROW_MEALS
    else:
        soaking_for = SOAKING_FOR_TODAY_DINNER
    result = asyncio.run(run_soaking_reminders(soaking_for=soaking_for))
    sys.exit(0 if result.get("success", False) else 1)
