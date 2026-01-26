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
            # Fetch user profile from database (only active users)
            user_result = self.supabase.table('user_profiles') \
                .select('*') \
                .eq('id', user_id) \
                .eq('is_active', True) \
                .execute()
            
            if not user_result.data or len(user_result.data) == 0:
                raise ValueError(f"User not found with user_id: {user_id} or account has been deactivated")
            
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
    
    def _build_system_prompt(
        self, 
        meal_items: List[Dict[str, Any]], 
        custom_dynamic_part: Optional[str] = None
    ) -> str:
        """
        Build the system prompt with meal items and guidelines.
        
        Args:
            meal_items: List of meal items from database
            custom_dynamic_part: Optional custom dynamic part (Part 1) to replace default rules
            
        Returns:
            Complete system prompt with Part 1 (dynamic) and Part 2 (static: meal items + output format)
        """
        meal_items_json = json.dumps(meal_items, indent=2, default=str)
        
        # Part 1: Dynamic part (can be customized)
        if custom_dynamic_part:
            dynamic_part = custom_dynamic_part.strip()
        else:
            dynamic_part = """You are an expert Indian meal planner. Your task is to create a balanced, nutritious, and culturally appropriate 7-day meal plan for Indian users.

CRITICAL RULE: Generate ALL 7 days at once in a single cohesive response. Do NOT plan each day independently. Plan the entire week holistically.

CRITICAL: Each meal item has meal type flags (is_breakfast, is_lunch, is_dinner, is_snacks):
- For BREAKFAST: ONLY use items where is_breakfast = True
- For LUNCH: ONLY use items where is_lunch = True
- For DINNER: ONLY use items where is_dinner = True
- For SNACKS: ONLY use items where is_snacks = True
Always check these flags before selecting items for each meal type.

CRITICAL RESTRICTIONS:
- Breakfast items (like Poha, Upma, Idli, Dosa, Chilla, Uttapam, Paratha, etc.) are STRICTLY FOR BREAKFAST ONLY - they MUST NEVER appear in lunch or dinner
- If an item has is_breakfast = True but is_lunch = False and is_dinner = False, it CANNOT be used in lunch or dinner, even if you think it might work
- Poha, Upma, and other breakfast-specific items are breakfast-only items - do NOT use them in lunch or dinner

HARD RULES:

1. NO REPETITION OF SABJIS, CURRIES, DAL VARIETIES, OR BREAKFAST ITEMS (ABSOLUTE RULE - NO EXCEPTIONS):
   - CRITICAL: Each sabji or curry dish must appear ONLY ONCE in the entire 7-day meal plan - this is a HARD RULE with NO EXCEPTIONS
   - This includes ALL sabjis and curries: Chhole Sabji, Rajmah Sabji, Aloo Sabji, Gobi Sabji, Baingan Sabji, Mix Vegetable, Egg Curry, Chicken Curry, Fish Curry, and ANY other sabji or curry dish
   - CRITICAL EXAMPLES: If you used "Egg Curry" on Day 6, you CANNOT use it again on Day 7 or any other day. If you used "Chhole Sabji" on Day 4, you CANNOT use it again on Day 5 or any other day. Same applies to ALL curries and sabjis.
   - Use different sabjis and curries for each day - explore ALL available options from the meal items list
   - Do NOT repeat the same vegetable dish (sabji) or curry within the 7-day period - each sabji/curry must appear ONLY ONCE across all 7 days
   - Before finalizing the meal plan, verify that NO sabji or curry appears more than once across all 7 days - check every single sabji and curry dish
   - CRITICAL: Breakfast main items (Idli, Dosa, Chilla, Uttapam, Paratha, Poha, Upma, etc.) must NOT repeat more than 2 times in the 7-day period. Rotate between different breakfast items across all 7 days to ensure variety.
   - CRITICAL: DAL VARIETY IS MANDATORY - There are MANY different dal varieties available in the meal items list (e.g., Toor Dal, Moong Dal, Chana Dal, Masoor Dal, Urad Dal, Mixed Dal, etc.). You MUST use DIFFERENT dal varieties across the 7-day period. Do NOT use the same dal variety (like "Mixed Dal") more than 2 times in 7 days. Rotate between different dal varieties - explore ALL available dal options from the meal items list.

2. FAVORITE CUISINES - 30% RULE:
   - If user has favorite cuisines specified, exactly 30% of the 7-day meal plan (approximately 8-9 meals out of 28 total meals) must include items from those favorite cuisines
   - Distribute these cuisine-specific meals across breakfast, lunch, snacks, and dinner appropriately
   - Plan the respective meal items from the available meal items list that match the favorite cuisines

3. NUTRITION PREFERENCES:
   - Strictly respect and incorporate user's nutrition preferences (e.g., High Protein, Low Carb, High Fiber, etc.)
   - Plan meals accordingly to meet these nutrition goals throughout the week
   - Select meal items that align with the specified nutrition preferences

4. EXTRA INSTRUCTIONS:
   - Carefully read and respect any extra instructions provided by the user
   - Incorporate these instructions into the meal planning logic

5. DIETARY RESTRICTIONS:
   - Strictly respect dietary_pattern (Vegetarian, Vegan, Eggetarian, Non-Vegetarian, etc.)
   - Honor medical_restrictions (Diabetes, Hypertension, Heart Disease, etc.) - avoid items that conflict with these restrictions
   - Respect dietary_restrictions (No Onion No Garlic, Gluten-Free, etc.) - completely avoid restricted items
   - If an item conflicts with any restriction, DO NOT include it in the meal plan

BEST COMBINATION PRACTICES (Follow these rules strictly):

1. Paratha (main item) goes with:
   - Raita OR Curd OR Chutney (mint chutney, tomato chutney - NOT coconut chutney)
   - CRITICAL: Curd/Raita/Chutney should ONLY be included if Paratha is the main breakfast item. Do NOT add Curd/Raita to other breakfast items.

2. Roti or Chapati (main/base items) goes with:
   - MANDATORY COMBINATION: When Roti or Chapati is selected for lunch/dinner, you MUST include:
     * Exactly ONE Dal (choose one dal variety - explore ALL available dal varieties from the meal items list, do NOT default to only "Mixed Dal")
     * Exactly ONE Sabji or Curry (choose one sabji or curry dish)
     * Salad
   - NOTE: This applies to lunch/dinner, not breakfast
   - CRITICAL: Do NOT serve Roti/Chapati without Dal, Sabji/Curry, and Salad - all three components are mandatory
   - CRITICAL: Rotate between different dal varieties across the week - there are many dal options available (Toor Dal, Moong Dal, Chana Dal, Masoor Dal, Urad Dal, Mixed Dal, etc.). Do NOT use the same dal variety repeatedly.

3. Biryani or Pulao goes with:
   - Raita
   - NOTE: This applies to lunch/dinner, not breakfast

4. Batter items (Idly, Chilla, Dosa, Uttapam) go with:
   - Chutney ONLY (mint chutney, tomato chutney, coconut chutney, etc.)
   - CRITICAL: 
     * MANDATORY: When a batter item (Idly/Chilla/Dosa/Uttapam) is selected, you MUST include a Chutney item. Batter items are typically served with chutney - do NOT serve them alone.
     * Chutney should ONLY be included if the batter item (Idly/Chilla/Dosa/Uttapam) is present. Do NOT add Chutney to other breakfast items.
     * Do NOT pair Idly with Sambar in breakfast - Sambar is typically for lunch/dinner, not breakfast. Idly goes with Chutney only.
     * Each batter item (Idly, Chilla, Dosa, Uttapam) is a MAIN item - you can only have ONE main item per breakfast. Do NOT pair two main items together (e.g., do NOT pair Idly with Chilla, or Dosa with Uttapam).

5. Single/Standalone items (do NOT pair with other items - serve alone):
   - Poha (BREAKFAST ONLY - do NOT use in lunch or dinner)
   - Upma (BREAKFAST ONLY - do NOT use in lunch or dinner)
   - Sandwiches
   - Burger
   - Wraps
   - Fried Rice
   - CRITICAL: These items are complete meals by themselves. Do NOT add Curd, Raita, Chutney, or any other accompaniments to these items.
   - CRITICAL: Poha and Upma are STRICTLY breakfast items - they MUST NOT appear in lunch or dinner. Always check the meal type flags (is_breakfast, is_lunch, is_dinner) before selecting items.

6. Rice (main/base item) goes with:
   - MANDATORY COMBINATION: When Rice is selected for lunch/dinner, you MUST include:
     * Exactly ONE Dal (choose one dal variety - explore ALL available dal varieties from the meal items list, do NOT default to only "Mixed Dal")
     * Exactly ONE Sabji or Curry (choose one sabji or curry dish)
     * Salad
   - NOTE: This applies to lunch/dinner, not breakfast
   - CRITICAL: Do NOT serve Rice without Dal, Sabji/Curry, and Salad - all three components are mandatory
   - CRITICAL: Rotate between different dal varieties across the week - there are many dal options available (Toor Dal, Moong Dal, Chana Dal, Masoor Dal, Urad Dal, Mixed Dal, etc.). Do NOT use the same dal variety repeatedly.

7. Seasonal Fruits:
   - Include seasonal fruits in breakfast, snacks, dinner, and lunch when appropriate
   - Consider the current season based on the provided date:
     * WINTER (Dec-Feb): apples, berries, guava, oranges
     * SUMMER (Mar-May): mango, watermelon, muskmelon, cucumber
     * MONSOON (Jun-Sep): seasonal fruits available during monsoon
     * POST-MONSOON/AUTUMN (Oct-Nov): transitional seasonal fruits
   - CRITICAL: Fruits are optional accompaniments, not mandatory. Do NOT add fruits to every single meal.

MEAL STRUCTURE:

BREAKFAST (1-2 items):
- ONLY select items where is_breakfast = True
- CRITICAL RULE: You can have ONLY ONE main breakfast item per meal. If you have 2 items, one must be the main item and the other must be an accompaniment (like Chutney, Raita, or Curd), NOT another main item.
- DO NOT pair two main items together (e.g., do NOT pair Idly with Chilla, Dosa with Uttapam, Paratha with Poha, etc.). A household would NOT make two main breakfast items in one meal.
- Follow combination rules above STRICTLY:
  * If Paratha is selected, you MUST add Raita OR Curd OR Chutney (choose ONE, not all) - Paratha is typically served with an accompaniment
  * If Batter items (Idly/Chilla/Dosa/Uttapam) are selected, you MUST add Chutney (choose one chutney type) - Batter items are typically served with chutney, do NOT serve them alone
  * If Standalone items (Poha/Upma/Sandwiches/Burger/Wraps/Fried Rice) are selected, serve them ALONE - do NOT add any accompaniments
  * Do NOT add Curd, Raita, Chutney, or Sambar to breakfast items that don't require them
- Include seasonal fruits when appropriate (optional, not mandatory for every breakfast)
- Rotate breakfast items across all 7 days - do NOT use the same main breakfast item more than 2 times in 7 days

LUNCH (3-4 items):
- ONLY select items where is_lunch = True
- CRITICAL: Do NOT use breakfast items (like Poha, Upma, Idli, Dosa, Chilla, Uttapam, Paratha, etc.) in lunch - these are breakfast-only items
- MANDATORY PATTERN when Rice, Roti, or Chapati is selected:
  * Base Grain (Rice/Roti/Chapati) + ONE Dal + ONE Sabji or Curry + Salad
  * CRITICAL: If Rice, Roti, or Chapati is included, you MUST include exactly ONE Dal, exactly ONE Sabji or Curry, and Salad. All four components are mandatory.
  * CRITICAL: When selecting Dal, choose a DIFFERENT dal variety from previous days. There are many dal varieties available (Toor Dal, Moong Dal, Chana Dal, Masoor Dal, Urad Dal, Mixed Dal, etc.) - use different ones across the week. Do NOT use the same dal variety more than 2 times in 7 days.
- Alternative pattern: Complete dish (Biryani/Pulao) + Raita
- CRITICAL: Do NOT repeat any sabji or curry that was already used in a previous day's lunch or dinner. Each sabji/curry (including Egg Curry, Chicken Curry, Fish Curry, and all vegetable sabjis) must appear ONLY ONCE in the entire 7-day plan. If "Egg Curry" was used on Day 6, it CANNOT be used again on Day 7 or any other day.
- Include seasonal fruits when appropriate

SNACKS (1-2 items):
- ONLY select items where is_snacks = True
- Light and healthy options
- Include seasonal fruits when appropriate

DINNER (3-4 items):
- ONLY select items where is_dinner = True
- CRITICAL: Do NOT use breakfast items (like Poha, Upma, Idli, Dosa, Chilla, Uttapam, Paratha, etc.) in dinner - these are breakfast-only items
- Similar pattern to lunch but can be lighter
- MANDATORY PATTERN when Rice, Roti, or Chapati is selected:
  * Base Grain (Rice/Roti/Chapati) + ONE Dal + ONE Sabji or Curry + Salad
  * CRITICAL: If Rice, Roti, or Chapati is included, you MUST include exactly ONE Dal, exactly ONE Sabji or Curry, and Salad. All four components are mandatory.
  * CRITICAL: When selecting Dal, choose a DIFFERENT dal variety from previous days. There are many dal varieties available (Toor Dal, Moong Dal, Chana Dal, Masoor Dal, Urad Dal, Mixed Dal, etc.) - use different ones across the week. Do NOT use the same dal variety more than 2 times in 7 days.
- Alternative pattern: Complete dish (Biryani/Pulao) + Raita
- CRITICAL: Do NOT repeat any sabji or curry that was already used in a previous day's lunch or dinner. Each sabji/curry (including Egg Curry, Chicken Curry, Fish Curry, and all vegetable sabjis) must appear ONLY ONCE in the entire 7-day plan. If "Egg Curry" was used on Day 6, it CANNOT be used again on Day 7 or any other day.
- Include seasonal fruits when appropriate

CRITICAL OUTPUT REQUIREMENTS:
- Generate ALL 7 days in ONE response - do NOT generate days separately
- Each meal type should have 1-3 items (typically 1-2 for breakfast/snacks, 2-4 for lunch/dinner)
- The meal_plan array must contain exactly 7 entries (one for each day)
- CRITICAL VALIDATION: Before returning the JSON, verify that:
  * NO breakfast items (like Poha, Upma, Idli, Dosa, Chilla, Uttapam, Paratha, etc.) appear in lunch or dinner. These items are STRICTLY for breakfast only. If you see "Poha" in dinner, it is WRONG - remove it immediately.
  * NO sabji or curry dish appears more than once across all 7 days. This includes ALL curries like Egg Curry, Chicken Curry, Fish Curry, and ALL sabjis like Chhole Sabji, Rajmah Sabji, Aloo Sabji, etc. If you see "Egg Curry" on Day 6, it MUST NOT appear on Day 7 or any other day. If you see "Chhole Sabji" on Day 4, it MUST NOT appear on Day 5 or any other day. Same for ALL sabjis and curries - each must appear ONLY ONCE.
  * NO dal variety appears more than 2 times across all 7 days. If you see "Mixed Dal" on Day 1 and Day 2, you MUST use a DIFFERENT dal variety (like Toor Dal, Moong Dal, Chana Dal, etc.) for the remaining days. Rotate between different dal varieties.
- Return ONLY the JSON, no additional text, explanation, or markdown formatting"""
        
        # Part 2: Static part (meal items JSON + output format - cannot be customized)
        static_part = f"""
AVAILABLE MEAL ITEMS:
{meal_items_json}

CRITICAL: You MUST understand and use ALL meal items from the JSON above. When selecting items:
- Use meal item IDs and names EXACTLY as they appear in the available meal items list
- Ensure all meal items exist in the provided meal items list
- Explore ALL available options from the meal items list to ensure variety

OUTPUT FORMAT:
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
}}"""
        
        # Combine Part 1 (dynamic) + Part 2 (static)
        system_prompt = dynamic_part + static_part
        
        return system_prompt
    
    def _build_user_prompt_part1(self, start_date: datetime, custom_part1: Optional[str] = None) -> str:
        """
        Build Part 1 of user prompt (dynamic instructions).
        
        Args:
            start_date: Start date for the meal plan
            custom_part1: Optional custom Part 1 to replace default instructions
            
        Returns:
            Part 1 of user prompt (dynamic instructions)
        """
        if custom_part1:
            return custom_part1.strip()
        
        # Build date range
        dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        current_date = start_date.strftime("%Y-%m-%d")
        
        default_part1 = f"""Generate a 7-day meal plan starting from {current_date}.

CURRENT DATE: {current_date}
(Determine the current season based on this date and Indian geography: Winter (Dec-Feb), Summer (Mar-May), Monsoon (Jun-Sep), Post-Monsoon/Autumn (Oct-Nov))

DATES FOR MEAL PLAN:
{chr(10).join([f"Day {i+1}: {date}" for i, date in enumerate(dates)])}

Generate a balanced, varied, and culturally appropriate 7-day meal plan for this user. Consider the season based on the current date ({current_date}) and Indian geography. 

CRITICAL: You MUST follow ALL requirements, instructions, guidelines, and rules specified in the system prompt, including:
- All IMPORTANT GUIDELINES (Balance, Seasonal Considerations, Meal Combination Principles, Meal Structure Principles, Dietary Restrictions, Variety and Repetition rules)
- All CRITICAL REQUIREMENTS FOR ALL MEAL PLANS
- All CRITICAL INSTRUCTIONS FOR PLANNING
- The OUTPUT FORMAT specification

IMPORTANT REMINDERS FOR THIS USER:
- User preferences listed below are MANDATORY - include them 2-4 times per week in the appropriate meal types
- Plan the entire week together to ensure proper variety, rotation, and distribution
- Return the complete JSON response with all 7 days specified in the exact format defined in the system prompt"""
        
        return default_part1
    
    def _build_user_prompt_part2(self, user_details: Dict[str, Any]) -> str:
        """
        Build Part 2 of user prompt (user preferences - static).
        
        Args:
            user_details: User details with preferences
            
        Returns:
            Part 2 of user prompt (user preferences)
        """
        part2 = f"""
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

ADDITIONAL NOTES: {user_details.get('extra_input', 'None')}"""
        
        return part2
    
    def _build_user_prompt(
        self, 
        user_details: Dict[str, Any], 
        start_date: datetime,
        custom_part1: Optional[str] = None
    ) -> str:
        """
        Build the complete user prompt with Part 1 (dynamic) and Part 2 (user preferences).
        
        Args:
            user_details: User details with preferences
            start_date: Start date for the meal plan
            custom_part1: Optional custom Part 1 to replace default instructions
            
        Returns:
            Complete user prompt combining Part 1 + Part 2
        """
        part1 = self._build_user_prompt_part1(start_date, custom_part1)
        part2 = self._build_user_prompt_part2(user_details)
        
        # Combine Part 1 (dynamic) + Part 2 (static user preferences)
        user_prompt = part1 + part2
        
        return user_prompt
    
    async def get_prompts(
        self,
        user_id: str,
        start_date: Optional[datetime] = None
    ) -> Dict[str, str]:
        """
        Get the system and user prompts that would be used for meal plan generation.
        Useful for debugging and saving prompts.
        
        Args:
            user_id: UUID of the user
            start_date: Optional start date (defaults to today)
            
        Returns:
            dict: Contains 'system_prompt' and 'user_prompt' keys
            
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
            system_prompt = self._build_system_prompt(meal_items, None)
            user_prompt = self._build_user_prompt(user_details, start_date, None)
            
            return {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt
            }
            
        except ValueError:
            raise
        except Exception as e:
            print(f"Error getting prompts: {str(e)}")
            raise
    
    async def generate_meal_plan(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        custom_system_prompt_part: Optional[str] = None,
        custom_user_prompt_part1: Optional[str] = None
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
            
            # Build prompts (use custom if provided, otherwise use defaults)
            system_prompt = self._build_system_prompt(meal_items, custom_system_prompt_part)
            
            # Build user prompt with Part 1 (dynamic) and Part 2 (user preferences - always included)
            user_prompt = self._build_user_prompt(user_details, start_date, custom_user_prompt_part1)
            
            # Call OpenAI API with retry logic for better outcomes
            max_retries = 2
            meal_plan_data = None
            
            for attempt in range(max_retries + 1):
                try:
                    # Use gpt-4o for better quality (or keep gpt-4o-mini for cost savings)
                    # Lower temperature (0.5) for more consistent, deterministic results
                    # Higher temperature (0.7-0.9) for more creativity/variety
                    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Allow override via env
                    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.5"))  # Lower for consistency
                    
                    response = self.openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
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
                            if attempt < max_retries:
                                print(f"JSON parse error on attempt {attempt + 1}, retrying...")
                                continue
                            raise ValueError(f"Failed to parse JSON from OpenAI response: {str(e)}")
                    
                    # Validate and structure response
                    if "meal_plan" not in meal_plan_data:
                        if attempt < max_retries:
                            print(f"Invalid format on attempt {attempt + 1}, retrying...")
                            continue
                        raise ValueError("Invalid meal plan format from OpenAI")
                    
                    # Success - break out of retry loop
                    break
                    
                except Exception as e:
                    if attempt < max_retries:
                        print(f"Error on attempt {attempt + 1}: {str(e)}, retrying...")
                        continue
                    raise
            
            if meal_plan_data is None:
                raise ValueError("Failed to generate valid meal plan after all retries")
            
            # Ensure user_id is set correctly
            meal_plan_data["user_id"] = user_id
            
            return meal_plan_data
            
        except ValueError:
            raise
        except Exception as e:
            print(f"Error generating meal plan: {str(e)}")
            raise
    
    async def generate_meal_plan_with_custom_prompts(
        self,
        user_id: str,
        system_prompt: str,
        user_prompt: str,
        start_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate a 7-day meal plan using OpenAI with custom system and user prompts.
        
        This method allows testing different prompt combinations without modifying
        the default prompt building logic.
        
        Args:
            user_id: UUID of the user
            system_prompt: Custom system prompt
            user_prompt: Custom user prompt
            start_date: Optional start date (defaults to today)
            
        Returns:
            dict: Generated meal plan in JSON format with user_id, day-wise, meal_type-wise meal items
            
        Raises:
            ValueError: If user is not found or prompts are invalid
            Exception: For other errors
        """
        try:
            # Validate user exists (we need to fetch meal items anyway)
            await self.get_user_details_with_preferences(user_id)
            
            # Set start date to today if not provided
            if start_date is None:
                start_date = datetime.now()
            
            # Fetch all meal items
            meal_items = self._fetch_all_meal_items()
            
            if not meal_items:
                raise ValueError("No meal items found in database")
            
            # Validate prompts are not empty
            if not system_prompt or not system_prompt.strip():
                raise ValueError("System prompt cannot be empty")
            if not user_prompt or not user_prompt.strip():
                raise ValueError("User prompt cannot be empty")
            
            # Call OpenAI API with custom prompts (using same retry logic)
            max_retries = 2
            meal_plan_data = None
            
            for attempt in range(max_retries + 1):
                try:
                    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.5"))
                    
                    response = self.openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
                        response_format={"type": "json_object"}
                    )
                    
                    response_content = response.choices[0].message.content
                    
                    try:
                        meal_plan_data = json.loads(response_content)
                    except json.JSONDecodeError as e:
                        import re
                        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
                        if json_match:
                            meal_plan_data = json.loads(json_match.group())
                        else:
                            if attempt < max_retries:
                                print(f"JSON parse error on attempt {attempt + 1}, retrying...")
                                continue
                            raise ValueError(f"Failed to parse JSON from OpenAI response: {str(e)}")
                    
                    if "meal_plan" not in meal_plan_data:
                        if attempt < max_retries:
                            print(f"Invalid format on attempt {attempt + 1}, retrying...")
                            continue
                        raise ValueError("Invalid meal plan format from OpenAI")
                    
                    # Success - break out of retry loop
                    break
                    
                except Exception as e:
                    if attempt < max_retries:
                        print(f"Error on attempt {attempt + 1}: {str(e)}, retrying...")
                        continue
                    raise
            
            if meal_plan_data is None:
                raise ValueError("Failed to generate valid meal plan after all retries")
            
            meal_plan_data["user_id"] = user_id
            return meal_plan_data
            
        except ValueError:
            raise
        except Exception as e:
            print(f"Error generating meal plan with custom prompts: {str(e)}")
            raise


# Create singleton instance
meal_generation_service = MealGenerationService()
