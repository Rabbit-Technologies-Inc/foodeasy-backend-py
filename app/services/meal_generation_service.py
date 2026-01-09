# app/services/meal_generation_service.py

from app.services.supabase_client import get_supabase_admin
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from openai import OpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()


class MealGenerationService:
    """
    Service class for fetching user details and generating meal plans.
    """
    
    def __init__(self):
        self.supabase = get_supabase_admin()
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def get_user_details_with_preferences(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Fetch user details along with all preferences from the database.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            dict: User details including:
                - Basic profile info (id)
                - Demographics (age, gender, total_household_adults, total_household_children)
                - Goals and restrictions (goals, medical_restrictions, dietary_restrictions)
                - Dietary preferences (dietary_pattern, nutrition_preferences, spice_level)
                - Cuisine preferences (cuisines_preferences)
                - Meal preferences (breakfast_preferences, lunch_preferences, snacks_preferences, dinner_preferences)
                - Additional input (extra_input)
                - Any other custom metadata
                
        Raises:
            ValueError: If user is not found
            Exception: For other database errors
        """
        try:
            # Fetch user profile from database
            user_result = self.supabase.table('user_profiles') \
                .select('*') \
                .eq('id', user_id) \
                .execute()
            
            if not user_result.data or len(user_result.data) == 0:
                raise ValueError(f"User not found with user_id: {user_id}")
            
            user = user_result.data[0]
            
            # Extract metadata (preferences are stored here)
            metadata = user.get('metadata', {})
            if not isinstance(metadata, dict):
                metadata = {}
            
            # Structure the response with all user details and preferences
            user_details = {
                # Basic profile information
                'id': user.get('id'),
                
                # Demographics (from metadata)
                'age': metadata.get('age'),
                'gender': metadata.get('gender'),
                'total_household_adults': metadata.get('total_household_adults'),
                'total_household_children': metadata.get('total_household_children'),
                
                # Goals and restrictions
                'goals': metadata.get('goals', []),
                'medical_restrictions': metadata.get('medical_restrictions', []),
                'dietary_restrictions': metadata.get('dietary_restrictions', []),
                
                # Dietary preferences
                'dietary_pattern': metadata.get('dietary_pattern'),
                'nutrition_preferences': metadata.get('nutrition_preferences', []),
                'spice_level': metadata.get('spice_level'),
                
                # Cuisine preferences
                'cuisines_preferences': metadata.get('cuisines_preferences', []),
                
                # Meal-specific preferences
                'breakfast_preferences': metadata.get('breakfast_preferences', []),
                'lunch_preferences': metadata.get('lunch_preferences', []),
                'snacks_preferences': metadata.get('snacks_preferences', []),
                'dinner_preferences': metadata.get('dinner_preferences', []),
                
                # Additional input
                'extra_input': metadata.get('extra_input'),
                
                # Include any other custom metadata fields
                'custom_metadata': {
                    k: v for k, v in metadata.items() 
                    if k not in [
                        'age', 'gender', 'total_household_adults', 'total_household_children',
                        'goals', 'medical_restrictions', 'dietary_restrictions',
                        'dietary_pattern', 'nutrition_preferences', 'spice_level',
                        'cuisines_preferences',
                        'breakfast_preferences', 'lunch_preferences', 'snacks_preferences', 'dinner_preferences',
                        'extra_input'
                    ]
                }
            }
            
            return user_details
            
        except ValueError:
            raise
        except Exception as e:
            print(f"Error fetching user details: {str(e)}")
            raise
    
    def _fetch_all_meal_items(self) -> List[Dict[str, Any]]:
        """Fetch all active meal items from the database"""
        try:
            response = self.supabase.table("meal_items") \
                .select("*") \
                .eq("is_active", True) \
                .order("id") \
                .execute()
            
            # Remove created_at and is_active from each item
            meal_items = [
                {k: v for k, v in item.items() if k not in ["created_at", "is_active"]}
                for item in response.data
            ]
            
            return meal_items
        except Exception as e:
            print(f"Error fetching meal items: {str(e)}")
            raise
    
    def _build_system_prompt(self, meal_items: List[Dict[str, Any]]) -> str:
        """Build the system prompt with meal items and guidelines"""
        meal_items_json = json.dumps(meal_items, indent=2, default=str)
        
        system_prompt = f"""You are an expert Indian meal planner. Your task is to create a balanced, nutritious, and culturally appropriate 7-day meal plan for Indian users.

CRITICAL: Plan ALL 7 days together as a cohesive weekly meal plan. Do NOT plan each day independently. Consider the entire week holistically when making decisions about variety, repetition, and meal distribution. Generate the complete 7-day plan in one cohesive response.

AVAILABLE MEAL ITEMS:
{meal_items_json}

CRITICAL: Each meal item has meal type flags (is_breakfast, is_lunch, is_dinner, is_snacks). 
- For BREAKFAST: ONLY use items where is_breakfast = True
- For LUNCH: ONLY use items where is_lunch = True
- For DINNER: ONLY use items where is_dinner = True
- For SNACKS: ONLY use items where is_snacks = True
Always check these flags before selecting items for each meal type.

IMPORTANT GUIDELINES:

1. BALANCE IS KEY - USER PREFERENCES ARE PRIORITY:
   - CRITICAL: If user has meal-specific preferences (breakfast_preferences, lunch_preferences, dinner_preferences, snacks_preferences), you MUST include those items in the corresponding meal types
   - User preferences are HIGH PRIORITY - include preferred items 2-4 times per week in the appropriate meal types
   - Match items from user preferences to available meal items and ensure they appear in the meal plan
   - If user selects "High Protein" as a goal, distribute protein-rich items throughout the week, not in every meal
   - If user selects a favorite cuisine, include it 2-3 times per week, not daily
   - Most Indians prefer comfort food: Base grains (Rice/Roti) with Dal, Indian Sabjis, Salads for lunch and dinner
   - Mix in variety: Include different cuisines and meal types 3-4 times per week to add excitement
   - AVOID REPETITION: Do not use the same item in every single meal. Rotate between different base grains, proteins, and vegetables
   - BUT: Always prioritize user preferences - ensure items from user preferences appear in the appropriate meal types

2. SEASONAL CONSIDERATIONS (Based on Indian Geography):
   - Determine the current season based on the provided date and Indian climate patterns:
     * WINTER (Dec-Feb): Include soups, warm beverages, seasonal fruits (apples, berries, guava, oranges)
     * SUMMER (Mar-May): Include buttermilk, cooling items, seasonal fruits (mango, watermelon, muskmelon, cucumber)
     * MONSOON (Jun-Sep): Include warm, light meals, avoid heavy fried items
     * POST-MONSOON/AUTUMN (Oct-Nov): Transitional season, mix of warm and light meals
   - Consider seasonal availability and preferences based on Indian geography

3. MEAL COMBINATION PRINCIPLES (Think like an Indian mom/nutritionist):

   CORE INDIAN MEAL PAIRING LOGIC (Critical - follow these rules):
   - Batter items (Dosa, Idli, Chilla, etc.) go well with Chutneys - use VARIETY of chutneys (mint chutney, tomato chutney, coconut chutney, etc.), not just one type
   - Single/Standalone items (Poha, Upma, Sandwiches, Burgers, Wraps, Scrambled Eggs) are Standalone - serve them alone, don't add extra items
   - Paratha goes well with Raita items and related chutney items (mint chutney, tomato chutney - NOT coconut chutney or sweet chutneys)
   - Biryani/Pulao BEST goes with Raita items - this is the ideal pairing
   - Rice/Roti goes well with Indian Sabjis, Stir Fries, and Salad
   - Eggs/Omelette items should be paired with bread/roti items, NOT with chutneys
   - Scrambled Eggs is a standalone item - serve it alone, don't pair with Rice/Roti or other items
   - Egg curry is typically a standalone dish or goes with Rice/Roti, but NOT with Steamed Rice as a common dinner pattern
   - LIQUID ITEMS RULE: Dal is a liquid item. If you include Dal, do NOT include another liquid item (like liquid sabjis, Rajmah Sabji, etc.). Instead, pair Dal with stir fry items or thick gravy items
   - AVOID: Two liquid items together (Dal + liquid sabji) - use one liquid (Dal) + one stir fry or thick gravy item

   BREAKFAST PRINCIPLES (1-2 items, keep it simple):
   - Look at available meal items and identify which are breakfast items (typically light, energizing foods)
   - Batter items (like Dosa, Idli, Chilla) should be paired with Chutneys - use VARIETY of chutneys available (mint, tomato, coconut, etc.), rotate them
   - Standalone items (like Poha, Upma, Sandwiches, Burgers, Wraps, Scrambled Eggs) should be served alone - don't add extra items
   - Paratha should be paired with Raita or related chutney items (mint chutney, tomato chutney - NOT coconut chutney)
   - Eggs/Omelette items should be paired with bread/roti items, NOT with chutneys
   - Scrambled Eggs is standalone - serve it alone
   - AVOID: 
     * Redundant combinations (don't add extra accompaniments if the main item already includes them)
     * Mixing breakfast items with lunch/dinner items
     * Eggs with chutneys (eggs go with bread/roti)
     * Adding extra items to standalone items (Poha, Upma, Sandwiches, Burgers, Wraps, Scrambled Eggs are complete by themselves)
     * Using the same chutney type repeatedly - use variety of chutneys available

   LUNCH/DINNER PRINCIPLES (3-4 items, MANDATORY PATTERN):
   - Identify base grains from available meal items (look for items that serve as the main carbohydrate base)
   - CRITICAL: If user has items in lunch_preferences or dinner_preferences, those items can be used as base grains or components for that meal type
   - Identify protein sources from available meal items (look for legumes, dals, protein-rich items)
   - Identify vegetable dishes from available meal items (look for sabjis, curries, vegetable preparations)
   - Identify accompaniments from available meal items (look for salads, raitas, pickles, etc.)
   - PRIMARY PATTERN: Base Grain + Protein + Vegetable + Accompaniment
   - Use this pattern 4-5 times per week
   - Base grains should be paired with Indian Sabjis, Stir Fries, and Salad
   - Complete dishes (one-pot meals like Biryani/Pulao) BEST go with Raita items - this is the ideal pairing
   - Complete dishes (one-pot meals) can be served with accompaniments
   - CRITICAL: EVERY lunch and dinner MUST include a base grain OR a complete dish - you cannot have side dishes/curries without a base
   - IMPORTANT: Rotate between different base grains - don't use the same base every day, but prioritize user preferences when they exist
   - LIQUID ITEMS RULE: Dal is a liquid item. If you include Dal, do NOT include another liquid item (like liquid sabjis, Rajmah Sabji, etc.). Instead, pair Dal with stir fry items or thick gravy items
   - AVOID: 
     * Side dishes/curries without a base grain (Indian meals need a base to eat with)
     * Breakfast items in lunch/dinner
     * Mixing incompatible meal types
     * Standalone items (Sandwiches, Burgers, Wraps, Scrambled Eggs) in lunch/dinner - these are complete meals by themselves
     * Common inappropriate combinations like Steamed Rice + Egg curry as a regular dinner pattern - Egg curry is typically standalone or needs proper Indian meal structure
     * Using Steamed Rice too frequently - rotate with Roti, Biryani, Pulao, etc.
     * Two liquid items together (Dal + liquid sabji like Rajmah Sabji) - use one liquid (Dal) + one stir fry or thick gravy item

4. MEAL STRUCTURE PRINCIPLES (Think like an Indian mom planning meals):

   BREAKFAST (1-2 items, keep it simple and appropriate):
   - CRITICAL: ONLY select items where is_breakfast = True from the available meal items
   - Pair items logically: items that come with accompaniments should be paired appropriately (all must have is_breakfast = True)
   - Standalone breakfast items can be served alone
   - Eggs should be paired with bread/roti items (that have is_breakfast = True), NOT with chutneys
   - AVOID mixing breakfast items with lunch items
   - AVOID redundant combinations (don't add extra accompaniments if main item already includes them)

   LUNCH (Main meal - 3-4 items, following Indian meal pattern):
   - CRITICAL: ONLY select items where is_lunch = True from the available meal items
   - MANDATORY PATTERN: Base Grain + Protein + Vegetable + Accompaniment (all must have is_lunch = True)
   - Can also be: Complete dish (one-pot meal) + Accompaniments (all must have is_lunch = True)
   - CRITICAL: You CANNOT have side dishes, curries, or any vegetable preparations without a base grain - every lunch MUST have either a base grain or a complete dish
   - LIQUID ITEMS RULE: If you include Dal (liquid), do NOT include another liquid item (like liquid sabjis, Rajmah Sabji). Instead, pair Dal with stir fry items or thick gravy items
   - Rotate between different base grains - don't use the same base every day
   - Include complete dishes 2-3 times per week if user prefers them
   - NEVER use items that don't have is_lunch = True
   - AVOID: Two liquid items together (Dal + liquid sabji) - use one liquid (Dal) + one stir fry or thick gravy item

   SNACKS (1-2 items, light and healthy):
   - CRITICAL: ONLY select items where is_snacks = True from the available meal items
   - Keep it simple and nutritious

   DINNER (3-4 items, lighter than lunch but balanced):
   - CRITICAL: ONLY select items where is_dinner = True from the available meal items
   - MANDATORY PATTERN: Base Grain + Protein + Vegetable + Accompaniment (all must have is_dinner = True)
   - CRITICAL: You CANNOT have side dishes, curries, or any vegetable preparations without a base grain - every dinner MUST have either a base grain or a complete dish
   - LIQUID ITEMS RULE: If you include Dal (liquid), do NOT include another liquid item (like liquid sabjis, Rajmah Sabji). Instead, pair Dal with stir fry items or thick gravy items
   - If lunch had one type of base grain, dinner can have a different base grain for variety
   - Can be lighter versions: Complete dish (one-pot meal) + Accompaniments, or Base + Protein + Vegetable (all must have is_dinner = True)
   - NEVER use items that don't have is_dinner = True
   - NEVER have side dishes/curries without a base grain - think like an Indian mom, you need a base to eat with
   - AVOID: Two liquid items together (Dal + liquid sabji) - use one liquid (Dal) + one stir fry or thick gravy item

5. DIETARY RESTRICTIONS:
   - Strictly respect dietary_pattern (Vegetarian, Vegan, Eggetarian, etc.)
   - Honor medical_restrictions (Diabetes, Hypertension, etc.)
   - Respect dietary_restrictions (No Onion No Garlic, etc.)

6. VARIETY AND REPETITION (CRITICAL):
   - Avoid repeating the same item more than 2-3 times in 7 days
   - DO NOT use the same base grain in every single meal - rotate between different base grains
   - VEGETABLE DISHES (Sabjis, curries) MUST NOT REPEAT within the 7-day period - use a different vegetable dish each day
   - BREAKFAST VARIETY IS CRITICAL: Do NOT repeat the same breakfast item more than 2 times in 7 days
   - Rotate breakfast items across all 7 days - ensure variety across all 7 days
   - If user has specific preferences, ensure they appear multiple times (2-4 times per week) but not every day
   - Ensure variety across days - each day should feel different
   - Balance traditional Indian meals with occasional international cuisines based on available items
   - User preferences are preferences, not exclusive requirements - include them frequently but mix intelligently
   - AVOID: Using the same breakfast on most days - rotate between different breakfast options

7. OUTPUT FORMAT:
   CRITICAL: Generate ALL 7 days at once in a single response. Do NOT generate days one by one or in a loop.
   
   You must return ONLY valid JSON in this exact format with ALL 7 days included:
   {{
     "user_id": "string",
     "meal_plan": [
       {{
         "day": 1,
         "date": "YYYY-MM-DD",
         "meals": {{
           "breakfast": [
             {{"id": "meal_item_id", "name": "meal_item_name"}},
             ...
           ],
           "lunch": [
             {{"id": "meal_item_id", "name": "meal_item_name"}},
             ...
           ],
           "snacks": [
             {{"id": "meal_item_id", "name": "meal_item_name"}},
             ...
           ],
           "dinner": [
             {{"id": "meal_item_id", "name": "meal_item_name"}},
             ...
           ]
         }}
       }},
       {{
         "day": 2,
         "date": "YYYY-MM-DD",
         "meals": {{ ... }}
       }},
       ... (continue for all 7 days: day 1 through day 7)
     ]
   }}

   - Generate ALL 7 days in ONE response - do not generate days separately
   - Use meal item IDs and names from the available meal items list
   - Each meal type should have 1-3 items (typically 1-2 for breakfast/snacks, 2-4 for lunch/dinner)
   - Ensure all meal items exist in the provided list
   - The meal_plan array must contain exactly 7 entries (one for each day)
   - Return ONLY the JSON, no additional text or explanation"""
        
        return system_prompt
    
    def _build_user_prompt(self, user_details: Dict[str, Any], start_date: datetime) -> str:
        """Build the user prompt with user preferences"""
        # Build date range
        dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        current_date = start_date.strftime("%Y-%m-%d")
        
        user_prompt = f"""Generate a 7-day meal plan starting from {current_date}.

CURRENT DATE: {current_date}
(Determine the current season based on this date and Indian geography: Winter (Dec-Feb), Summer (Mar-May), Monsoon (Jun-Sep), Post-Monsoon/Autumn (Oct-Nov))

USER PROFILE:
- User ID: {user_details.get('id')}
- Age: {user_details.get('age', 'Not specified')}
- Gender: {user_details.get('gender', 'Not specified')}
- Household: {user_details.get('total_household_adults', 1)} adults, {user_details.get('total_household_children', 0)} children

GOALS: {', '.join(user_details.get('goals', [])) if user_details.get('goals') else 'None specified'}

MEDICAL RESTRICTIONS: {', '.join(user_details.get('medical_restrictions', [])) if user_details.get('medical_restrictions') else 'None'}

DIETARY RESTRICTIONS: {', '.join(user_details.get('dietary_restrictions', [])) if user_details.get('dietary_restrictions') else 'None'}

DIETARY PATTERN: {user_details.get('dietary_pattern', 'Not specified')}

NUTRITION PREFERENCES: {', '.join(user_details.get('nutrition_preferences', [])) if user_details.get('nutrition_preferences') else 'None'}

SPICE LEVEL: {user_details.get('spice_level', 'Not specified')}

FAVORITE CUISINES: {', '.join(user_details.get('cuisines_preferences', [])) if user_details.get('cuisines_preferences') else 'None'}

MEAL PREFERENCES:
- Breakfast: {', '.join(user_details.get('breakfast_preferences', [])) if user_details.get('breakfast_preferences') else 'None'}
- Lunch: {', '.join(user_details.get('lunch_preferences', [])) if user_details.get('lunch_preferences') else 'None'}
- Snacks: {', '.join(user_details.get('snacks_preferences', [])) if user_details.get('snacks_preferences') else 'None'}
- Dinner: {', '.join(user_details.get('dinner_preferences', [])) if user_details.get('dinner_preferences') else 'None'}

ADDITIONAL NOTES: {user_details.get('extra_input', 'None')}

DATES FOR MEAL PLAN:
{chr(10).join([f"Day {i+1}: {date}" for i, date in enumerate(dates)])}

CRITICAL REQUIREMENTS:
1. USER PREFERENCES ARE MANDATORY: If user has meal-specific preferences listed above, you MUST include those items in the corresponding meal types:
   - Match items from user preferences to available meal items in the database
   - Include preferred items 2-4 times per week in the appropriate meal types (breakfast preferences in breakfast, lunch preferences in lunch, etc.)
   - Ensure items from user preferences appear in the meal plan - they are not optional
2. DO NOT use the same base item in every single meal - rotate between different base grains, but prioritize user preferences when they exist
3. Follow the Base Grain + Protein + Vegetable + Accompaniment pattern for lunch and dinner (4-5 times per week), but include user preferences when specified
4. VEGETABLE DISHES (Sabjis, curries) MUST NOT REPEAT - use a different vegetable dish for each day in the 7-day plan
5. BREAKFAST VARIETY IS CRITICAL: Rotate breakfast items across all 7 days - do NOT use the same breakfast more than 2 times in 7 days
6. Use different breakfast options from available items - ensure each day has a different breakfast feel
7. User preferences are HIGH PRIORITY - include them frequently (2-4 times per week) in the appropriate meal types, but also mix in other suitable items intelligently
8. Ensure variety - each day should feel different, especially breakfast - avoid repetitive patterns

CRITICAL INSTRUCTIONS:
1. Plan ALL 7 days together as a cohesive weekly meal plan - do NOT plan each day independently
2. When planning, consider the entire week holistically:
   - Ensure different sabjis across all 7 days (no repetition)
   - Rotate Rice/Roti/Biryani/Pulao across the week
   - Distribute user preferences (like Biryani) across multiple days (2-4 times)
   - Plan variety across the entire week, not just individual days
3. Think of this as planning a complete weekly menu, not 7 separate daily menus
4. Generate the complete 7-day plan in one cohesive response

Generate a balanced, varied, and culturally appropriate meal plan for all 7 days following all the guidelines. Consider the season based on the current date and Indian geography. Plan the entire week together to ensure proper variety, rotation, and distribution. Return the complete JSON response with all 7 days specified."""
        
        return user_prompt
    
    async def generate_meal_plan(
        self,
        user_id: str,
        start_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate a 7-day meal plan using OpenAI based on user preferences.
        
        Args:
            user_id: UUID of the user
            start_date: Optional start date (defaults to today)
            
        Returns:
            dict: Generated meal plan in JSON format with user_id, day-wise, meal_type-wise meal items
            
        Raises:
            ValueError: If user is not found
            Exception: For other errors
        """
        try:
            # Get user details
            user_details = await self.get_user_details_with_preferences(user_id)
            
            # Set start date to today if not provided
            if start_date is None:
                start_date = datetime.now()
            
            # Fetch all meal items
            meal_items = self._fetch_all_meal_items()
            
            if not meal_items:
                raise ValueError("No meal items found in database")
            
            # Build prompts
            system_prompt = self._build_system_prompt(meal_items)
            user_prompt = self._build_user_prompt(user_details, start_date)
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # or "gpt-4" for better results
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            
            # Parse response
            response_content = response.choices[0].message.content
            
            # Parse JSON response
            try:
                meal_plan_data = json.loads(response_content)
            except json.JSONDecodeError as e:
                # Try to extract JSON from response if wrapped in markdown
                import re
                json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
                if json_match:
                    meal_plan_data = json.loads(json_match.group())
                else:
                    raise ValueError(f"Failed to parse JSON from OpenAI response: {str(e)}")
            
            # Validate and structure response
            if "meal_plan" not in meal_plan_data:
                raise ValueError("Invalid meal plan format from OpenAI")
            
            # Ensure user_id is set correctly
            meal_plan_data["user_id"] = user_id
            
            return meal_plan_data
            
        except ValueError:
            raise
        except Exception as e:
            print(f"Error generating meal plan: {str(e)}")
            raise


# Create singleton instance
meal_generation_service = MealGenerationService()
