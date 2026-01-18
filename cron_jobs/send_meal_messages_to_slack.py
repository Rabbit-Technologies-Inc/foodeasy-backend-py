#!/usr/bin/env python3
"""
CRON job to generate and send meal messages to Slack for all active users.

This script:
1. Fetches all active users with active meal plans
2. For each user, generates messages for breakfast, lunch, snacks, and dinner
3. If user has a cook with non-English language, includes translated text and voice note
4. Sends formatted messages to Slack webhook

Usage:
    python cron_jobs/send_meal_messages_to_slack.py
"""

import os
import sys
import logging
import asyncio
import base64
import httpx
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.supabase_client import get_supabase_admin
from app.services.meal_messaging_service import meal_messaging_service
from app.services.cook_service import cook_service

# Load environment variables
load_dotenv()

# Configure logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f"meal_messages_slack_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def get_meal_type_mapping(supabase) -> Dict[str, int]:
    """
    Get mapping of meal type names to meal_type_id from database.
    Returns dict like: {"breakfast": 1, "lunch": 2, "snacks": 3, "dinner": 4}
    """
    try:
        response = supabase.table("meal_types") \
            .select("id, name") \
            .eq("is_active", True) \
            .execute()
        
        mapping = {}
        for meal_type in response.data:
            name = meal_type.get("name", "").lower().strip()
            meal_id = meal_type.get("id")
            if name and meal_id:
                mapping[name] = meal_id
        
        # Ensure we have all required meal types
        breakfast_id = None
        lunch_id = None
        snacks_id = None
        dinner_id = None
        
        for name, meal_id in mapping.items():
            if "breakfast" in name:
                breakfast_id = meal_id
            elif "lunch" in name:
                lunch_id = meal_id
            elif "snack" in name:
                snacks_id = meal_id
            elif "dinner" in name:
                dinner_id = meal_id
        
        # Create final mapping with standard keys
        final_mapping = {}
        if breakfast_id:
            final_mapping["breakfast"] = breakfast_id
        if lunch_id:
            final_mapping["lunch"] = lunch_id
        if snacks_id:
            final_mapping["snacks"] = snacks_id
        if dinner_id:
            final_mapping["dinner"] = dinner_id
        
        # If we couldn't find meal types, use fallback defaults
        if not final_mapping:
            final_mapping = {
                "breakfast": 1,
                "lunch": 2,
                "snacks": 3,
                "dinner": 4
            }
        
        return final_mapping
    except Exception as e:
        logger.warning(f"Could not fetch meal types from database: {e}")
        return {
            "breakfast": 1,
            "lunch": 2,
            "snacks": 3,
            "dinner": 4
        }


async def get_active_users_with_meal_plans(supabase) -> List[Dict[str, Any]]:
    """
    Get all active users who have active meal plans for today.
    
    Returns:
        List of user dictionaries with user_id, name, and active meal plan info
    """
    try:
        today = date.today().isoformat()
        
        # Get all active meal plans that include today
        meal_plans_response = supabase.table("user_meal_plan") \
            .select("user_id, id") \
            .eq("is_active", True) \
            .lte("start_date", today) \
            .gte("end_date", today) \
            .execute()
        
        if not meal_plans_response.data:
            logger.info("No active meal plans found for today")
            return []
        
        # Get unique user IDs
        user_ids = list(set([plan["user_id"] for plan in meal_plans_response.data]))
        
        # Get user profiles
        users_response = supabase.table("user_profiles") \
            .select("id, full_name") \
            .in_("id", user_ids) \
            .execute()
        
        # Create a mapping of user_id to user info
        users_dict = {user["id"]: user for user in users_response.data}
        
        # Combine meal plan info with user info
        users_with_plans = []
        for plan in meal_plans_response.data:
            user_id = plan["user_id"]
            if user_id in users_dict:
                users_with_plans.append({
                    "user_id": user_id,
                    "user_name": users_dict[user_id].get("full_name", "Unknown"),
                    "meal_plan_id": plan["id"]
                })
        
        logger.info(f"Found {len(users_with_plans)} active users with meal plans for today")
        return users_with_plans
        
    except Exception as e:
        logger.error(f"Error fetching active users with meal plans: {str(e)}", exc_info=True)
        return []


async def generate_all_meal_messages(
    user_id: str,
    cook: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate all meal messages for a user for TODAY ONLY in one call (more efficient).
    
    Returns:
        Dictionary with all meal data for today or None if no meals found
    """
    try:
        today = date.today()
        # Call service once to get ALL meal types for TODAY at once (more efficient)
        result = await meal_messaging_service.generate_meal_messages(
            user_id=user_id,
            cook_id=cook.get("id") if cook else None,
            target_date=today,  # Explicitly use today's date
            meal_type_id=None  # Get all meal types at once
        )
        
        if not result.get("success"):
            return None
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating meal messages for {user_id}: {str(e)}", exc_info=True)
        return None


def format_meal_message(meal_type: str, meal_items: List[str]) -> str:
    """
    Format a message for a specific meal type.
    
    Args:
        meal_type: Name of the meal type (breakfast, lunch, etc.)
        meal_items: List of meal item names
        
    Returns:
        Formatted message string
    """
    if not meal_items:
        return ""
    
    if len(meal_items) == 1:
        items_text = meal_items[0]
    elif len(meal_items) == 2:
        items_text = f"{meal_items[0]} and {meal_items[1]}"
    else:
        items_text = ", ".join(meal_items[:-1]) + f", and {meal_items[-1]}"
    
    return f"Today's {meal_type.capitalize()} is {items_text}"


async def upload_voice_note_to_slack(
    audio_base64: str,
    filename: str,
    slack_bot_token: str,
    channel: Optional[str] = None
) -> Optional[str]:
    """
    Upload MP3 voice note to Slack using Files API.
    
    Args:
        audio_base64: Base64 encoded audio data
        filename: Name for the file
        slack_bot_token: Slack bot token (xoxb-...)
        channel: Optional channel ID to post to (if not provided, uses default from webhook)
        
    Returns:
        File URL if successful, None otherwise
    """
    try:
        # Decode base64 audio
        audio_data = base64.b64decode(audio_base64)
        
        # Upload to Slack using Files API
        url = "https://slack.com/api/files.upload"
        headers = {
            "Authorization": f"Bearer {slack_bot_token}"
        }
        
        # Prepare multipart form data
        files = {
            "file": (filename, audio_data, "audio/mpeg")
        }
        
        data = {
            "filename": filename,
            "title": filename
        }
        
        if channel:
            data["channels"] = channel
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Use files parameter for multipart/form-data
            response = await client.post(
                url,
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    file_url = result.get("file", {}).get("url_private")
                    logger.info(f"Successfully uploaded voice note to Slack: {filename}")
                    return file_url
                else:
                    logger.error(f"Slack API error: {result.get('error')}")
                    return None
            else:
                logger.error(f"Failed to upload to Slack: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error uploading voice note to Slack: {str(e)}", exc_info=True)
        return None


async def upload_voice_note_to_gcs(
    audio_base64: str,
    filename: str,
    bucket_name: Optional[str] = None
) -> Optional[str]:
    """
    Upload MP3 voice note to Google Cloud Storage and return public URL.
    
    Args:
        audio_base64: Base64 encoded audio data
        filename: Name for the file
        bucket_name: GCS bucket name (from env or parameter)
        
    Returns:
        Public URL if successful, None otherwise
    """
    try:
        from google.cloud import storage
        
        bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            logger.warning("GCS_BUCKET_NAME not set, cannot upload to GCS")
            return None
        
        # Decode base64 audio
        audio_data = base64.b64decode(audio_base64)
        
        # Initialize GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Upload file
        blob = bucket.blob(f"voice_notes/{filename}")
        blob.upload_from_string(audio_data, content_type="audio/mpeg")
        
        # Make it publicly accessible
        blob.make_public()
        
        public_url = blob.public_url
        logger.info(f"Successfully uploaded voice note to GCS: {public_url}")
        return public_url
        
    except ImportError:
        logger.warning("google-cloud-storage not installed, cannot upload to GCS")
        return None
    except Exception as e:
        logger.error(f"Error uploading voice note to GCS: {str(e)}", exc_info=True)
        return None


async def send_message_to_slack(
    user_id: str,
    user_name: str,
    meal_type: str,
    english_message: str,
    translated_message: Optional[str] = None,
    voice_note: Optional[Dict[str, Any]] = None,
    slack_webhook_url: str = None,
    slack_bot_token: Optional[str] = None,
    slack_channel: Optional[str] = None
) -> bool:
    """
    Send formatted message to Slack webhook.
    
    Returns:
        True if successful, False otherwise
    """
    if not slack_webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return False
    
    try:
        # Build the message text in the requested format
        message_parts = [
            f"user_id: {user_id}",
            f"user_name: {user_name}",
            f"meal_type: {meal_type}",
            "",
            english_message
        ]
        
        if translated_message:
            message_parts.append("")
            message_parts.append(translated_message)
        
        if voice_note and voice_note.get("audio_base64"):
            message_parts.append("")
            message_parts.append(f"[Voice note generated: MP3 format, {len(voice_note.get('audio_base64', ''))} bytes]")
        
        message_text = "\n".join(message_parts)
        
        # Prepare Slack payload with blocks for better formatting
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*user_id:* {user_id}\n*user_name:* {user_name}\n*meal_type:* {meal_type}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": english_message
                }
            }
        ]
        
        # Add translated message block if available
        if translated_message:
            blocks.append({
                "type": "divider"
            })
            blocks.append({
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": translated_message
                }
            })
        
        # Handle voice note - try to upload and share link
        voice_note_url = None
        if voice_note and voice_note.get("audio_base64"):
            audio_base64 = voice_note.get("audio_base64")
            filename = f"{user_id}_{meal_type}_{date.today().isoformat()}.mp3"
            
            # Try Slack Files API first (if bot token provided)
            if slack_bot_token:
                voice_note_url = await upload_voice_note_to_slack(
                    audio_base64=audio_base64,
                    filename=filename,
                    slack_bot_token=slack_bot_token,
                    channel=slack_channel
                )
            
            # Fallback to GCS if Slack upload failed or not available
            if not voice_note_url:
                voice_note_url = await upload_voice_note_to_gcs(
                    audio_base64=audio_base64,
                    filename=filename
                )
            
            # Add voice note info to message
            blocks.append({
                "type": "divider"
            })
            if voice_note_url:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Voice Note:* <{voice_note_url}|Download MP3>"
                    }
                })
                message_parts.append("")
                message_parts.append(f"Voice Note: {voice_note_url}")
            else:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Voice Note:* Generated (MP3 format, {len(audio_base64)} bytes) - *Upload failed*"
                    }
                })
                message_parts.append("")
                message_parts.append(f"[Voice note generated but upload failed: MP3 format, {len(audio_base64)} bytes]")
        
        payload = {
            "text": message_text,
            "blocks": blocks
        }
        
        # Send to Slack
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(slack_webhook_url, json=payload)
            
            if response.status_code == 200:
                logger.info(f"Successfully sent {meal_type} message to Slack for user {user_id}")
                return True
            else:
                logger.error(f"Failed to send to Slack: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending message to Slack: {str(e)}", exc_info=True)
        return False


async def process_user_meals(
    user_info: Dict[str, Any],
    meal_type_mapping: Dict[str, int],
    slack_webhook_url: str
) -> Dict[str, Any]:
    """
    Process all meal types for a single user.
    
    This function calls MealMessagingService ONCE per user to get all meals,
    then processes each meal type individually for Slack.
    
    Returns:
        Dictionary with processing results
    """
    user_id = user_info["user_id"]
    user_name = user_info["user_name"]
    
    logger.info(f"Processing meals for user {user_id} ({user_name})")
    
    # Get cook information once
    cooks = await cook_service.get_user_cooks(user_id)
    cook = cooks[0] if cooks else None
    
    results = {
        "user_id": user_id,
        "user_name": user_name,
        "meals_processed": 0,
        "meals_sent": 0,
        "errors": []
    }
    
    # Generate ALL meal messages in one call (more efficient)
    all_meals_result = await generate_all_meal_messages(user_id, cook)
    
    if not all_meals_result:
        logger.info(f"No meal plan found for today for user {user_id} ({user_name}) - skipping")
        return results
    
    meals_by_type = all_meals_result.get("meals", {})
    
    # Check if user has any meals for today - if not, skip entirely
    if not meals_by_type or len(meals_by_type) == 0:
        logger.info(f"User {user_id} ({user_name}) has no meals scheduled for today - skipping")
        return results
    
    cook_info = all_meals_result.get("cook")
    cook_language_code = cook_info.get("language", "en") if cook_info else "en"
    
    # Process each meal type from the result
    for meal_type in ["breakfast", "lunch", "snacks", "dinner"]:
        if meal_type not in meals_by_type or not meals_by_type[meal_type]:
            logger.debug(f"No {meal_type} found for user {user_id}")
            continue
        
        try:
            # Format the English message
            meal_items = meals_by_type[meal_type]
            english_message = format_meal_message(meal_type, meal_items)
            
            if not english_message:
                continue
            
            results["meals_processed"] += 1
            
            # Translate and generate voice note if cook has non-English language
            translated_message = None
            voice_note = None
            
            if cook_info and cook_language_code != "en":
                # Translate just this meal type's message
                translated_message = await meal_messaging_service._translate_text(
                    english_message,
                    cook_language_code
                )
                
                # Generate voice note for translated message
                voice_note = await meal_messaging_service._generate_voice_note(translated_message)
            
            # Send to Slack
            success = await send_message_to_slack(
                user_id=user_id,
                user_name=user_name,
                meal_type=meal_type,
                english_message=english_message,
                translated_message=translated_message,
                voice_note=voice_note,
                slack_webhook_url=slack_webhook_url,
                slack_bot_token=os.getenv("SLACK_BOT_TOKEN"),
                slack_channel=os.getenv("SLACK_CHANNEL")
            )
            
            if success:
                results["meals_sent"] += 1
            else:
                results["errors"].append(f"Failed to send {meal_type} to Slack")
                
        except Exception as e:
            error_msg = f"Error processing {meal_type} for user {user_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)
    
    return results


async def main():
    """
    Main function that will be executed by the CRON job.
    """
    try:
        today = date.today()
        logger.info("=" * 60)
        logger.info("Starting meal messages to Slack CRON job")
        logger.info(f"Processing meals for: {today.isoformat()} (TODAY ONLY)")
        logger.info("=" * 60)
        
        # Get Slack webhook URL from environment
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook_url:
            logger.error("SLACK_WEBHOOK_URL environment variable is not set")
            return 1
        
        # Check for optional Slack bot token (for file uploads)
        slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
        if slack_bot_token:
            logger.info("SLACK_BOT_TOKEN found - will use Files API for voice note uploads")
        else:
            logger.info("SLACK_BOT_TOKEN not set - will try GCS for voice note uploads (if configured)")
        
        # Check for GCS bucket (fallback for voice notes)
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        if gcs_bucket:
            logger.info(f"GCS_BUCKET_NAME found: {gcs_bucket} - will use for voice note uploads if needed")
        
        # Get Supabase client
        supabase = get_supabase_admin()
        
        # Get meal type mapping
        logger.info("Fetching meal type mapping...")
        meal_type_mapping = await get_meal_type_mapping(supabase)
        logger.info(f"Meal type mapping: {meal_type_mapping}")
        
        # Get active users with meal plans for TODAY ONLY
        logger.info(f"Fetching active users with meal plans for {today.isoformat()}...")
        users = await get_active_users_with_meal_plans(supabase)
        
        if not users:
            logger.info("No active users with meal plans found. Exiting.")
            return 0
        
        # Process each user
        total_processed = 0
        total_sent = 0
        users_skipped = 0
        all_errors = []
        
        for user_info in users:
            try:
                result = await process_user_meals(
                    user_info=user_info,
                    meal_type_mapping=meal_type_mapping,
                    slack_webhook_url=slack_webhook_url
                )
                
                # Count skipped users (those with no meals for today)
                if result["meals_processed"] == 0 and len(result["errors"]) == 0:
                    users_skipped += 1
                
                total_processed += result["meals_processed"]
                total_sent += result["meals_sent"]
                all_errors.extend(result["errors"])
                
            except Exception as e:
                error_msg = f"Error processing user {user_info.get('user_id')}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                all_errors.append(error_msg)
        
        # Summary
        logger.info("=" * 60)
        logger.info("CRON job completed")
        logger.info(f"Users with active meal plans: {len(users)}")
        logger.info(f"Users skipped (no meals for today): {users_skipped}")
        logger.info(f"Users processed: {len(users) - users_skipped}")
        logger.info(f"Total meals processed: {total_processed}")
        logger.info(f"Total meals sent to Slack: {total_sent}")
        logger.info(f"Total errors: {len(all_errors)}")
        if all_errors:
            logger.warning("Errors encountered:")
            for error in all_errors:
                logger.warning(f"  - {error}")
        logger.info("=" * 60)
        
        return 0 if len(all_errors) == 0 else 1
        
    except Exception as e:
        logger.error(f"Error executing CRON job: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
