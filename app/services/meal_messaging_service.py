# app/services/meal_messaging_service.py

from app.services.supabase_client import get_supabase_admin
from app.services.cook_service import cook_service
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from googletrans import Translator


class MealMessagingService:
    """
    Service class for generating meal messages in English and cook's language.
    """
    
    def __init__(self):
        self.supabase = get_supabase_admin()
        # googletrans doesn't require initialization - it's free and unlimited
    
    def _get_cook_language(self, cook: Dict[str, Any]) -> str:
        """
        Get the cook's primary language.
        
        Args:
            cook: Cook data dictionary with languages_known field
            
        Returns:
            str: Language code (e.g., 'hi' for Hindi, 'en' for English)
        """
        languages_known = cook.get("languages_known", [])
        
        if not languages_known:
            return "en"  # Default to English
        
        # Get the first language (primary language)
        primary_language = languages_known[0]
        
        # Map common language names to language codes
        language_map = {
            "english": "en",
            "hindi": "hi",
            "tamil": "ta",
            "telugu": "te",
            "kannada": "kn",
            "malayalam": "ml",
            "bengali": "bn",
            "gujarati": "gu",
            "marathi": "mr",
            "punjabi": "pa",
            "urdu": "ur",
            "odia": "or",
            "assamese": "as",
        }
        
        # Convert to lowercase for matching
        primary_language_lower = primary_language.lower().strip()
        
        # Return mapped language code or default to English
        return language_map.get(primary_language_lower, "en")
    
    async def _translate_text(self, text: str, target_language: str) -> str:
        """
        Translate text to target language using googletrans library.
        
        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'hi', 'ta')
            
        Returns:
            str: Translated text, or original text if translation fails
        """
        # If target is English, return original
        if target_language == "en":
            return text
        
        try:
            # googletrans 4.0.2 has async translate method
            # Explicitly specify source language as 'en' to avoid auto-detection issues
            translator = Translator()
            result = await translator.translate(text, src='en', dest=target_language)
            translated_text = result.text
            print(f"Translation successful: '{text}' -> '{translated_text}' (lang: {target_language})")
            return translated_text
        except Exception as e:
            print(f"Error translating text '{text}' to {target_language}: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            # Return original text if translation fails
            return text
    
    async def _get_today_meal_plan(self, user_id: str, target_date: Optional[date] = None, meal_type_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get today's meal plan for a user.
        
        Args:
            user_id: UUID of the user
            target_date: Date to get meal plan for (defaults to today)
            meal_type_id: Optional meal type ID to filter by (e.g., 1 for breakfast)
            
        Returns:
            dict: Meal plan data structured by meal type
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        date_str = target_date.isoformat()
        
        # Get active meal plan for user
        meal_plan_response = self.supabase.table("user_meal_plan") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .lte("start_date", date_str) \
            .gte("end_date", date_str) \
            .order("id", desc=True) \
            .limit(1) \
            .execute()
        
        if not meal_plan_response.data or len(meal_plan_response.data) == 0:
            return {}
        
        user_meal_plan_id = meal_plan_response.data[0]["id"]
        
        # Get meal plan details for today
        details_query = self.supabase.table("user_meal_plan_details") \
            .select("""
                meal_type_id,
                meal_types (
                    id,
                    name
                ),
                meal_items (
                    id,
                    name
                )
            """) \
            .eq("user_meal_plan_id", user_meal_plan_id) \
            .eq("date", date_str) \
            .eq("is_active", True)
        
        # Filter by meal_type_id if provided
        if meal_type_id is not None:
            details_query = details_query.eq("meal_type_id", meal_type_id)
        
        details_response = details_query.order("meal_type_id").execute()
        
        # Structure meals by meal type
        meals_by_type = {}
        
        for detail in details_response.data:
            meal_type_data = detail.get("meal_types")
            meal_item_data = detail.get("meal_items")
            
            if not meal_type_data or not meal_item_data:
                continue
            
            # Handle meal_type_data - it might be a dict or list
            if isinstance(meal_type_data, list) and len(meal_type_data) > 0:
                meal_type_info = meal_type_data[0]
            elif isinstance(meal_type_data, dict):
                meal_type_info = meal_type_data
            else:
                continue
            
            # Handle meal_item_data - it might be a dict or list
            if isinstance(meal_item_data, list) and len(meal_item_data) > 0:
                meal_item_info = meal_item_data[0]
            elif isinstance(meal_item_data, dict):
                meal_item_info = meal_item_data
            else:
                continue
            
            meal_type_name = meal_type_info.get("name", "").lower()
            meal_item_name = meal_item_info.get("name", "")
            
            if meal_type_name and meal_item_name:
                if meal_type_name not in meals_by_type:
                    meals_by_type[meal_type_name] = []
                meals_by_type[meal_type_name].append(meal_item_name)
        
        return meals_by_type
    
    def _format_meal_message(self, meal_type: str, meal_items: List[str]) -> str:
        """
        Format a message for a specific meal type.
        
        Args:
            meal_type: Type of meal (breakfast, lunch, snacks, dinner)
            meal_items: List of meal item names
            
        Returns:
            str: Formatted message
        """
        if not meal_items:
            return ""
        
        # Capitalize meal type
        meal_type_capitalized = meal_type.capitalize()
        
        # Join meal items with comma and "and" for the last item
        if len(meal_items) == 1:
            items_text = meal_items[0]
        elif len(meal_items) == 2:
            items_text = f"{meal_items[0]} and {meal_items[1]}"
        else:
            items_text = ", ".join(meal_items[:-1]) + f", and {meal_items[-1]}"
        
        return f"Today's {meal_type_capitalized} is {items_text}"
    
    async def generate_meal_messages(
        self,
        user_id: str,
        cook_id: Optional[str] = None,
        target_date: Optional[date] = None,
        meal_type_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate meal messages in English and cook's language.
        
        Args:
            user_id: UUID of the user
            cook_id: Optional UUID of the cook (if not provided, uses first cook)
            target_date: Optional date (defaults to today)
            meal_type_id: Optional meal type ID to filter by (e.g., 1 for breakfast)
            
        Returns:
            dict: Messages in English and cook's language
        """
        if target_date is None:
            target_date = datetime.now().date()
        
        # Get today's meal plan
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
        
        # Handle case when no cook is found
        cook = None
        cook_language_code = "en"  # Default to English if no cook
        
        if cooks:
            # Use specified cook or first cook
            if cook_id:
                cook = next((c for c in cooks if c.get("id") == cook_id), None)
                if not cook:
                    # If specific cook_id provided but not found, still proceed with English only
                    print(f"Warning: Cook with id {cook_id} not found. Using English only.")
            else:
                cook = cooks[0]
            
            # Get cook's language if cook exists
            if cook:
                cook_language_code = self._get_cook_language(cook)
                print(f"DEBUG: Cook found - Name: {cook.get('name')}, Languages: {cook.get('languages_known')}, Language Code: {cook_language_code}")
        else:
            # No cook found - proceed with English only
            print(f"Info: No cook found for user {user_id}. Returning English messages only.")
        
        # Generate messages for each meal type
        messages_english = []
        messages_cook_language = []
        
        # Define meal type order
        meal_type_order = ["breakfast", "lunch", "snacks", "dinner"]
        
        for meal_type in meal_type_order:
            if meal_type in meals_by_type:
                meal_items = meals_by_type[meal_type]
                english_message = self._format_meal_message(meal_type, meal_items)
                
                if english_message:
                    messages_english.append(english_message)
                    
                    # Translate to cook's language if not English
                    if cook_language_code != "en":
                        print(f"DEBUG: Attempting to translate '{english_message}' to {cook_language_code}")
                        translated_message = await self._translate_text(
                            english_message,
                            cook_language_code
                        )
                        print(f"DEBUG: Translation result: '{translated_message}'")
                        messages_cook_language.append(translated_message)
                    else:
                        print(f"DEBUG: Skipping translation (language is English)")
                        messages_cook_language.append(english_message)
        
        # Combine all messages
        full_message_english = "\n".join(messages_english)
        
        if cook_language_code != "en":
            full_message_cook_language = "\n".join(messages_cook_language)
        else:
            full_message_cook_language = full_message_english
        
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
        
        # Add cook information if available
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
