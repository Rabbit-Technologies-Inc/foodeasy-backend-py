# app/services/meal_messaging_service.py

import os
import json
import base64
import httpx
import asyncio
from app.services.supabase_client import get_supabase_admin
from app.services.cook_service import cook_service
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from google.cloud import translate_v3
from google.oauth2 import service_account
from googletrans import Translator
from dotenv import load_dotenv

load_dotenv()


class MealMessagingService:
    """Service class for generating meal messages in English and cook's language."""
    
    def __init__(self):
        self.supabase = get_supabase_admin()
        self.elevenlabs_api_key = os.getenv("ELEVEN_LABS_API_KEY")
        self.elevenlabs_voice_id = os.getenv("ELEVEN_LABS_VOICE_ID")
        
        # Initialize Google Cloud Translation v3 client
        self.translate_client = None
        self.project_id = None
        
        google_credentials = os.getenv("GOOGLE_CLOUD_CREDENTIALS_JSON") or os.getenv("FIREBASE_CREDENTIALS_JSON")
        google_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        
        try:
            credentials = None
            if google_credentials:
                try:
                    creds_dict = json.loads(google_credentials)
                    credentials = service_account.Credentials.from_service_account_info(creds_dict)
                    self.project_id = creds_dict.get("project_id") or google_project_id
                except json.JSONDecodeError:
                    if os.path.exists(google_credentials):
                        credentials = service_account.Credentials.from_service_account_file(google_credentials)
                        with open(google_credentials, 'r') as f:
                            creds_dict = json.load(f)
                            self.project_id = creds_dict.get("project_id") or google_project_id
            
            if not self.project_id:
                self.project_id = google_project_id
            
            if credentials and self.project_id:
                self.translate_client = translate_v3.TranslationServiceClient(credentials=credentials)
            elif self.project_id:
                self.translate_client = translate_v3.TranslationServiceClient()
        except Exception as e:
            print(f"Warning: Could not initialize Google Cloud Translation client: {e}")
            self.translate_client = None
        
        # Initialize googletrans as fallback
        try:
            self.googletrans_translator = Translator()
        except Exception as e:
            print(f"Warning: Could not initialize googletrans fallback: {e}")
            self.googletrans_translator = None
    
    def _get_cook_language(self, cook: Dict[str, Any]) -> str:
        """Get the cook's primary language code."""
        languages_known = cook.get("languages_known", [])
        if not languages_known:
            return "en"
        
        language_map = {
            "english": "en", "hindi": "hi", "tamil": "ta", "telugu": "te",
            "kannada": "kn", "malayalam": "ml", "bengali": "bn", "gujarati": "gu",
            "marathi": "mr", "punjabi": "pa", "urdu": "ur", "odia": "or", "assamese": "as",
        }
        
        primary_language = languages_known[0].lower().strip()
        return language_map.get(primary_language, "en")
    
    async def _translate_text(self, text: str, target_language: str) -> str:
        """
        Translate text to target language.
        Priority: 1. Cloud Translation API, 2. googletrans, 3. original text
        """
        if target_language == "en":
            return text
        
        # Try Cloud Translation API first
        if self.translate_client and self.project_id:
            try:
                def translate_sync():
                    response = self.translate_client.translate_text(
                        contents=[text],
                        parent=f"projects/{self.project_id}/locations/global",
                        mime_type="text/plain",
                        source_language_code="en",
                        target_language_code=target_language,
                    )
                    return response.translations[0].translated_text if response.translations else text
                
                return await asyncio.to_thread(translate_sync)
            except Exception as e:
                if "PERMISSION_DENIED" not in str(e) and "permission" not in str(e).lower():
                    print(f"Cloud Translation API error: {str(e)}")
        
        # Fallback to googletrans
        if self.googletrans_translator:
            try:
                result = await self.googletrans_translator.translate(text, dest=target_language, src='en')
                return result.text
            except Exception as e:
                print(f"Googletrans error: {str(e)}")
        
        return text
    
    async def _get_today_meal_plan(self, user_id: str, target_date: Optional[date] = None, meal_type_id: Optional[int] = None) -> Dict[str, Any]:
        """Get meal plan for a user for the specified date."""
        if target_date is None:
            target_date = datetime.now().date()
        
        date_str = target_date.isoformat()
        
        meal_plan_response = self.supabase.table("user_meal_plan") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .lte("start_date", date_str) \
            .gte("end_date", date_str) \
            .order("id", desc=True) \
            .limit(1) \
            .execute()
        
        if not meal_plan_response.data:
            return {}
        
        user_meal_plan_id = meal_plan_response.data[0]["id"]
        
        details_query = self.supabase.table("user_meal_plan_details") \
            .select("""
                meal_type_id,
                meal_types (id, name),
                meal_items (id, name)
            """) \
            .eq("user_meal_plan_id", user_meal_plan_id) \
            .eq("date", date_str) \
            .eq("is_active", True)
        
        if meal_type_id is not None:
            details_query = details_query.eq("meal_type_id", meal_type_id)
        
        details_response = details_query.order("meal_type_id").execute()
        
        meals_by_type = {}
        for detail in details_response.data:
            meal_type_data = detail.get("meal_types")
            meal_item_data = detail.get("meal_items")
            
            if not meal_type_data or not meal_item_data:
                continue
            
            meal_type_info = meal_type_data[0] if isinstance(meal_type_data, list) else meal_type_data
            meal_item_info = meal_item_data[0] if isinstance(meal_item_data, list) else meal_item_data
            
            meal_type_name = meal_type_info.get("name", "").lower()
            meal_item_name = meal_item_info.get("name", "")
            
            if meal_type_name and meal_item_name:
                if meal_type_name not in meals_by_type:
                    meals_by_type[meal_type_name] = []
                meals_by_type[meal_type_name].append(meal_item_name)
        
        return meals_by_type
    
    def _format_meal_message(self, meal_type: str, meal_items: List[str]) -> str:
        """Format a message for a specific meal type."""
        if not meal_items:
            return ""
        
        if len(meal_items) == 1:
            items_text = meal_items[0]
        elif len(meal_items) == 2:
            items_text = f"{meal_items[0]} and {meal_items[1]}"
        else:
            items_text = ", ".join(meal_items[:-1]) + f", and {meal_items[-1]}"
        
        return f"Today's {meal_type.capitalize()} is {items_text}"
    
    async def _generate_voice_note(self, text: str) -> Optional[Dict[str, Any]]:
        """Generate voice note using ElevenLabs API."""
        if not self.elevenlabs_api_key or not self.elevenlabs_voice_id:
            return None
        
        try:
            # Get and validate voice settings
            model_id = os.getenv("ELEVEN_LABS_MODEL_ID", "eleven_multilingual_v2")
            stability = float(os.getenv("ELEVEN_LABS_VOICE_STABILITY", "0.5"))
            similarity_boost = float(os.getenv("ELEVEN_LABS_VOICE_SIMILARITY_BOOST", "0.75"))
            speed = float(os.getenv("ELEVEN_LABS_VOICE_SPEED", "1.0"))
            
            # Clamp values to valid ranges
            stability = max(0.0, min(1.0, stability))
            similarity_boost = max(0.0, min(1.0, similarity_boost))
            speed = max(0.25, min(4.0, speed))
            
            # Round stability to valid TTD values (0.0, 0.5, 1.0) for models that require it
            if stability < 0.25:
                stability = 0.0
            elif stability < 0.75:
                stability = 0.5
            else:
                stability = 1.0
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}?output_format=mp3_44100_128"
            headers = {"xi-api-key": self.elevenlabs_api_key, "Content-Type": "application/json"}
            payload = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "speed": speed
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    audio_base64 = base64.b64encode(response.content).decode('utf-8')
                    return {
                        "audio_base64": audio_base64,
                        "format": "mp3",
                        "sample_rate": 44100,
                        "bitrate": 128
                    }
                else:
                    error_json = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    print(f"ElevenLabs API error {response.status_code}: {error_json.get('detail', {}).get('message', 'Unknown error')}")
                    return None
                    
        except (ValueError, TypeError) as e:
            print(f"Invalid voice settings: {e}")
            return None
        except httpx.TimeoutException:
            print("ElevenLabs API timeout")
            return None
        except httpx.RequestError as e:
            print(f"ElevenLabs API network error: {e}")
            return None
        except Exception as e:
            print(f"Voice note generation error: {e}")
            return None
    
    async def generate_meal_messages(
        self,
        user_id: str,
        cook_id: Optional[str] = None,
        target_date: Optional[date] = None,
        meal_type_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate meal messages in English and cook's language."""
        if target_date is None:
            target_date = datetime.now().date()
        
        meals_by_type = await self._get_today_meal_plan(user_id, target_date, meal_type_id)
        if not meals_by_type:
            return {
                "success": False,
                "message": "No meal plan found for today",
                "date": target_date.isoformat(),
                "messages": {}
            }
        
        # Get cook information
        cooks = await cook_service.get_user_cooks(user_id)
        cook = None
        cook_language_code = "en"
        
        if cooks:
            cook = next((c for c in cooks if c.get("id") == cook_id), None) if cook_id else cooks[0]
            if cook:
                cook_language_code = self._get_cook_language(cook)
        
        # Generate messages for each meal type
        messages_english = []
        messages_cook_language = []
        
        for meal_type in ["breakfast", "lunch", "snacks", "dinner"]:
            if meal_type in meals_by_type:
                english_message = self._format_meal_message(meal_type, meals_by_type[meal_type])
                if english_message:
                    messages_english.append(english_message)
                    if cook_language_code != "en":
                        translated = await self._translate_text(english_message, cook_language_code)
                        messages_cook_language.append(translated)
                    else:
                        messages_cook_language.append(english_message)
        
        full_message_english = "\n".join(messages_english)
        full_message_cook_language = "\n".join(messages_cook_language) if cook_language_code != "en" else full_message_english
        
        # Generate voice note
        voice_note = None
        voice_note_error = None
        
        if cook and cook_language_code != "en":
            voice_note = await self._generate_voice_note(full_message_cook_language)
            if not voice_note:
                voice_note_error = "Voice note generation failed"
        elif not cook:
            voice_note_error = "No cook found"
        elif cook_language_code == "en":
            voice_note_error = "Cook language is English"
        
        # Prepare response
        response = {
            "success": True,
            "date": target_date.isoformat(),
            "messages": {
                "english": full_message_english,
                "cook_language": full_message_cook_language,
                "cook_language_code": cook_language_code
            },
            "meals": meals_by_type
        }
        
        if voice_note:
            response["voice_note"] = voice_note
        elif voice_note_error:
            response["voice_note_error"] = voice_note_error
        
        if cook:
            response["cook"] = {
                "id": cook.get("id"),
                "name": cook.get("name"),
                "language": cook_language_code,
                "languages_known": cook.get("languages_known", [])
            }
        else:
            response["cook"] = None
            response["message"] = "No cook found. Messages are in English only."
        
        return response


# Create singleton instance
meal_messaging_service = MealMessagingService()
