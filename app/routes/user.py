# app/routes/user.py

from fastapi import APIRouter, HTTPException, status, Depends, Query, Path, Response
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
from app.services.supabase_client import get_supabase_admin
from app.dependencies.auth import verify_user_access
from typing import Dict, Any, List, Optional

router = APIRouter(prefix="/user", tags=["User Management"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class UpdateUserProfileRequest(BaseModel):
    """Request to update user profile with metadata support"""
    # Basic profile fields
    full_name: Optional[str] = Field(None, min_length=1, max_length=100, description="User's full name")
    age: Optional[int] = Field(None, ge=1, le=120, description="User age")
    gender: Optional[str] = Field(None, description="Gender: male, female, other, prefer_not_to_say")
    total_household_adults: Optional[int] = Field(None, ge=1, description="Number of adults in household")
    total_household_children: Optional[int] = Field(None, ge=0, description="Number of children in household")
    
    # Metadata fields (will be merged with existing metadata)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Custom metadata to merge with existing metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "John Doe",
                "age": 28,
                "gender": "male",
                "total_household_adults": 2,
                "total_household_children": 1,
                "metadata": {
                    "preferences": {
                        "theme": "dark",
                        "notifications": True
                    },
                    "custom_field": "custom_value"
                }
            }
        }


class UpdateOnboardingRequest(BaseModel):
    """Request to update complete onboarding data - all values are TEXT, not IDs"""
    
    # Basic profile info
    full_name: Optional[str] = Field(None, min_length=1, max_length=100, description="User's full name")
    
    # Basic demographics
    age: Optional[int] = Field(None, ge=1, le=120, description="User age")
    gender: Optional[str] = Field(None, description="Gender: male, female, other, prefer_not_to_say")
    total_household_adults: Optional[int] = Field(1, ge=1, description="Number of adults in household")
    total_household_children: Optional[int] = Field(0, ge=0, description="Number of children in household")
    
    # Onboarding selections (all are TEXT values, not IDs)
    goals: List[str] = Field(default=[], description="Selected goal names (e.g., ['Weight Loss', 'Muscle Gain'])")
    medical_restrictions: List[str] = Field(default=[], description="Medical restriction names")
    dietary_pattern: Optional[str] = Field(None, description="Dietary pattern name (e.g., 'Vegetarian')")
    nutrition_preferences: List[str] = Field(default=[], description="Nutrition preference names")
    dietary_restrictions: List[str] = Field(default=[], description="Dietary restriction names")
    spice_level: Optional[str] = Field(None, description="Spice level name (e.g., 'Medium')")
    cooking_oil_preferences: List[str] = Field(default=[], description="Cooking oil names")
    cuisines_preferences: List[str] = Field(default=[], description="Cuisine names")
    breakfast_preferences: List[str] = Field(default=[], description="Breakfast item names")
    lunch_preferences: List[str] = Field(default=[], description="Lunch item names")
    snacks_preferences: List[str] = Field(default=[], description="Snack item names")
    dinner_preferences: List[str] = Field(default=[], description="Dinner item names")
    
    # Additional input
    extra_input: Optional[str] = Field(None, max_length=1000, description="Additional notes/preferences from user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "John Doe",
                "age": 28,
                "gender": "male",
                "total_household_adults": 2,
                "total_household_children": 1,
                "goals": ["Weight Loss", "Muscle Gain"],
                "medical_restrictions": ["Diabetes"],
                "dietary_pattern": "Vegetarian",
                "nutrition_preferences": ["High Protein"],
                "dietary_restrictions": ["No Onion No Garlic"],
                "spice_level": "Medium",
                "cooking_oil_preferences": ["Olive Oil", "Coconut Oil"],
                "cuisines_preferences": ["North Indian", "South Indian"],
                "breakfast_preferences": ["Idli", "Poha"],
                "lunch_preferences": ["Dal Rice"],
                "snacks_preferences": ["Samosa"],
                "dinner_preferences": ["Roti Sabzi"],
                "extra_input": "I prefer early dinner around 7 PM"
            }
        }


class SwapMealItemRequest(BaseModel):
    """Request to swap a meal item in a meal plan"""
    user_meal_plan_detail_id: int = Field(..., description="ID of the user_meal_plan_details record to swap", gt=0)
    new_meal_item_id: int = Field(..., description="ID of the new meal item to replace with", gt=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_meal_plan_detail_id": 123,
                "new_meal_item_id": 45
            }
        }


class AddMealItemRequest(BaseModel):
    """Request to add a meal item to a meal plan"""
    user_meal_plan_id: int = Field(..., description="ID of the user meal plan", gt=0)
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    meal_type_id: int = Field(..., description="ID of the meal type (breakfast, lunch, snacks, dinner)", gt=0)
    meal_item_id: int = Field(..., description="ID of the meal item to add", gt=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_meal_plan_id": 1,
                "date": "2024-01-01",
                "meal_type_id": 1,
                "meal_item_id": 45
            }
        }


class RemoveMealItemRequest(BaseModel):
    """Request to remove a meal item from a meal plan"""
    user_meal_plan_detail_id: int = Field(..., description="ID of the user_meal_plan_details record to remove", gt=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_meal_plan_detail_id": 123
            }
        }


# ============================================
# USER ENDPOINTS
# ============================================

@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Get user profile with metadata",
    description="""
    Retrieve complete user profile including all data and metadata.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Returns complete user profile with:**
    - Direct columns: user_id, phone_number, full_name, created_at, last_login
    - Metadata JSONB: Contains all other user data:
      - Demographics: age, gender, total_household_adults, total_household_children
      - Onboarding status: onboarding_completed, onboarding_completed_at
      - Onboarding preferences: goals, dietary_pattern, medical_restrictions, nutrition_preferences, etc.
      - Custom metadata: Any additional key-value pairs stored
    
    **Note:** Age, gender, household info, onboarding status, and preferences are all stored
    in the metadata JSONB column, not as separate table columns.
    """
)
async def get_user_profile(
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """Get complete user profile including metadata"""
    try:
        user = await auth_service.get_user_by_id(user_id)
        return {
            "success": True,
            "data": user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in get_user_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user profile: {str(e)}"
        )


@router.put(
    "/{user_id}/profile",
    status_code=status.HTTP_200_OK,
    summary="Update user profile with metadata",
    description="""
    Update user profile including basic fields and metadata.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    This endpoint allows updating:
    - Direct columns: full_name (stored in user_profiles table)
    - Metadata fields: age, gender, total_household_adults, total_household_children (stored in metadata JSONB)
    - Custom metadata: Additional JSON object that will be merged with existing metadata
    
    **Storage:**
    - `full_name` is stored as a direct column in the user_profiles table
    - `age`, `gender`, `total_household_adults`, `total_household_children` are stored in the metadata JSONB column
    - Custom metadata fields are also stored in the metadata JSONB column
    
    **Metadata handling:**
    - All metadata (including age, gender, household) is merged with existing metadata (not replaced)
    - Existing metadata keys will be updated, new keys will be added
    - To remove a metadata key, set it to null in the update
    
    **Protected fields:** Cannot update id, firebase_uid, phone_number, or created_at.
    
    **Example:**
    ```json
    {
        "full_name": "John Doe",
        "age": 28,
        "gender": "male",
        "total_household_adults": 2,
        "metadata": {
            "preferences": {"theme": "dark"},
            "custom_field": "value"
        }
    }
    ```
    """
)
async def update_user_profile(
    request: UpdateUserProfileRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """Update user profile with metadata support"""
    try:
        # Prepare update data
        update_data = request.dict(exclude_none=True)
        
        # Fields that should be stored in metadata (not direct columns)
        metadata_fields = ['age', 'gender', 'total_household_adults', 'total_household_children']
        
        # Get current user to merge metadata
        current_user = await auth_service.get_user_by_id(user_id)
        current_metadata = current_user.get('metadata', {})
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        
        # Move metadata-only fields from update_data to metadata
        metadata_to_update = {}
        for field in metadata_fields:
            if field in update_data:
                metadata_to_update[field] = update_data.pop(field)
        
        # Handle explicit metadata field if provided
        explicit_metadata = update_data.pop('metadata', None)
        if explicit_metadata is not None:
            if isinstance(explicit_metadata, dict):
                metadata_to_update.update(explicit_metadata)
            else:
                metadata_to_update = explicit_metadata
        
        # Merge all metadata updates with existing metadata
        if metadata_to_update:
            current_metadata.update(metadata_to_update)
            update_data['metadata'] = current_metadata
        
        if not update_data:
            raise ValueError("No fields provided to update")
        
        updated_user = await auth_service.update_user_profile(user_id, update_data)
        
        return {
            "success": True,
            "message": "User profile updated successfully",
            "data": updated_user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in update_user_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.put(
    "/{user_id}/onboarding",
    status_code=status.HTTP_200_OK,
    summary="Save complete onboarding data",
    description="""
    Save all user onboarding selections including full name.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **IMPORTANT:** Send actual TEXT values (names), NOT IDs.
    
    **Accepts:**
    - full_name: User's full name (stored as direct column)
    - All other onboarding data (stored in metadata JSONB)
    
    Example:
    - ✅ "goals": ["Weight Loss", "Muscle Gain"]
    - ❌ "goals": ["goal_id_1", "goal_id_2"]
    """
)
async def update_onboarding_data(
    request: UpdateOnboardingRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """Save complete onboarding data for user"""
    try:
        onboarding_data = request.dict(exclude_none=True)
        updated_user = await auth_service.update_onboarding_data(user_id, onboarding_data)
        
        return {
            "success": True,
            "message": "Onboarding data saved successfully",
            "data": updated_user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in update_onboarding_data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update onboarding data: {str(e)}"
        )


@router.get(
    "/{user_id}/onboarding-status",
    status_code=status.HTTP_200_OK,
    summary="Check onboarding completion status",
    description="""
    Check if user has completed the onboarding process.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    Returns:
    - onboarding_completed: Boolean indicating if onboarding is complete
    - onboarding_completed_at: ISO timestamp when onboarding was completed (if completed)
    - has_name: Boolean indicating if user has set their full name
    
    Use this endpoint to determine if user needs to complete onboarding flow.
    """
)
async def get_onboarding_status(
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """Get onboarding completion status"""
    try:
        status_data = await auth_service.get_onboarding_status(user_id)
        
        return {
            "success": True,
            "data": status_data
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get onboarding status: {str(e)}"
        )


# ============================================
# MEAL PLAN HELPER FUNCTIONS
# ============================================

async def _fetch_grocery_items_for_meal_items(meal_item_ids: List[int]) -> Dict[int, Dict[str, List[str]]]:
    """
    Fetch grocery items grouped by type for multiple meal items.
    
    Args:
        meal_item_ids: List of meal item IDs to fetch groceries for
        
    Returns:
        Dict mapping meal_item_id to grocery_items_by_type
        Example: {
            1: {"Grains": ["Rice", "Wheat"], "Vegetables": ["Tomato"]},
            2: {"Dairy": ["Milk", "Paneer"]}
        }
    """
    if not meal_item_ids:
        return {}
    
    supabase = get_supabase_admin()
    
    try:
        # Fetch ingredients for these meal items using the junction table
        ingredients_response = supabase.table("meal_item_ingredients") \
            .select("""
                meal_item_id,
                meal_ingredients (
                    name,
                    meal_ingredients_types (
                        name
                    )
                )
            """) \
            .in_("meal_item_id", meal_item_ids) \
            .eq("is_active", True) \
            .execute()
        
        # Group ingredients by meal_item_id and then by type
        meal_item_groceries = {}
        
        if ingredients_response.data:
            for item in ingredients_response.data:
                meal_item_id = item.get("meal_item_id")
                ingredient_data = item.get("meal_ingredients")
                
                if not ingredient_data or not meal_item_id:
                    continue
                
                # Initialize dict for this meal item if not exists
                if meal_item_id not in meal_item_groceries:
                    meal_item_groceries[meal_item_id] = {}
                
                # Get ingredient name and type
                ingredient_name = ingredient_data.get("name")
                ingredient_type_data = ingredient_data.get("meal_ingredients_types")
                
                if not ingredient_name:
                    continue
                
                # Get type name, default to "Uncategorized"
                type_name = "Uncategorized"
                if ingredient_type_data:
                    type_name = ingredient_type_data.get("name", "Uncategorized")
                
                # Add ingredient to the type list
                if type_name not in meal_item_groceries[meal_item_id]:
                    meal_item_groceries[meal_item_id][type_name] = []
                
                # Avoid duplicates
                if ingredient_name not in meal_item_groceries[meal_item_id][type_name]:
                    meal_item_groceries[meal_item_id][type_name].append(ingredient_name)
        
        return meal_item_groceries
        
    except Exception as e:
        print(f"Error fetching grocery items for meal items: {e}")
        return {}


def _structure_meal_plan_details(details_response_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Helper function to structure meal plan details hierarchically.
    
    Args:
        details_response_data: List of meal plan detail records with joined meal_types and meal_items
        
    Returns:
        List of date objects with hierarchical meal structure
    """
    dates_dict = {}
    
    for detail in details_response_data:
        detail_date = detail.get("date")
        if not detail_date:
            continue
        
        # Initialize date entry if not exists
        if detail_date not in dates_dict:
            dates_dict[detail_date] = {}
        
        # Get the id from user_meal_plan_details
        detail_id = detail.get("id")
        meal_type_id = detail.get("meal_type_id")
        meal_type_data = detail.get("meal_types")
        meal_item_data = detail.get("meal_items")
        
        # Skip if no meal_type_id
        if not meal_type_id:
            continue
        
        # Handle meal_type_data - it might be null, a dict, or a list
        meal_type_info = None
        if meal_type_data:
            if isinstance(meal_type_data, list) and len(meal_type_data) > 0:
                meal_type_info = meal_type_data[0]
            elif isinstance(meal_type_data, dict):
                meal_type_info = meal_type_data
        
        if not meal_type_info:
            continue
        
        # Initialize meal type entry if not exists
        if meal_type_id not in dates_dict[detail_date]:
            dates_dict[detail_date][meal_type_id] = {
                "id": meal_type_info.get("id"),
                "name": meal_type_info.get("name"),
                "description": meal_type_info.get("description"),
                "is_active": meal_type_info.get("is_active"),
                "created_at": meal_type_info.get("created_at"),
                "meal_items": []
            }
        
        # Add meal item if it exists
        # Note: Each detail record represents one meal item, so we append all items
        # Multiple items for the same meal type will be in separate detail records
        if meal_item_data:
            # Handle meal_item_data - it might be null, a dict, or a list
            meal_items_to_add = []
            if isinstance(meal_item_data, list):
                # If it's a list, add all items
                meal_items_to_add = meal_item_data
            elif isinstance(meal_item_data, dict):
                # If it's a dict, add as single item
                meal_items_to_add = [meal_item_data]
            
            # Add all meal items to the list
            for meal_item_info in meal_items_to_add:
                if meal_item_info:
                    # Remove is_active from meal item for cleaner response
                    meal_item_clean = {
                        k: v for k, v in meal_item_info.items() 
                        if k not in ["is_active"]
                    }
                    # Always add the user_meal_plan_details id to the meal item
                    # This is the primary key from user_meal_plan_details table
                    meal_item_clean["user_meal_plan_detail_id"] = detail_id
                    dates_dict[detail_date][meal_type_id]["meal_items"].append(meal_item_clean)
    
    # Convert to list format
    dates_list = []
    for date_str in sorted(dates_dict.keys()):
        meals_list = []
        for meal_type_id in sorted(dates_dict[date_str].keys()):
            meals_list.append(dates_dict[date_str][meal_type_id])
        
        dates_list.append({
            "date": date_str,
            "meals": meals_list
        })
    
    return dates_list


# ============================================
# MEAL PLAN ENDPOINTS
# ============================================

@router.get(
    "/{user_id}/meal-plans",
    status_code=status.HTTP_200_OK,
    summary="List user's meal plans",
    description="""
    Get a list of all meal plans for a user with optional filters.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Query Parameters:**
    - is_active: Filter by active status (true/false)
    - limit: Maximum number of plans to return (default: 100)
    - offset: Number of plans to skip for pagination (default: 0)
    
    **Response Structure:**
    ```json
    {
      "success": true,
      "data": [
        {
          "id": 1,
          "start_date": "2024-01-01",
          "end_date": "2024-01-07",
          "is_active": true,
          "created_at": "..."
        }
      ],
      "count": 1
    }
    ```
    
    Returns only meal plans belonging to the authenticated user.
    """
)
async def list_user_meal_plans(
    user_id: str = Depends(verify_user_access),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(100, description="Maximum number of plans to return", ge=1, le=1000),
    offset: int = Query(0, description="Number of plans to skip", ge=0)
) -> Dict[str, Any]:
    """
    List all meal plans for a user with optional filters.
    
    Returns:
        Dict containing success status and list of meal plans.
    """
    supabase = get_supabase_admin()
    
    try:
        query = supabase.table("user_meal_plan") \
            .select("*", count="exact") \
            .eq("user_id", user_id)
        
        # Apply filters
        if is_active is not None:
            query = query.eq("is_active", is_active)
        
        # Apply pagination
        query = query.order("created_at", desc=True) \
            .range(offset, offset + limit - 1)
        
        response = query.execute()
        
        return {
            "success": True,
            "data": response.data,
            "count": len(response.data),
            "total": response.count if hasattr(response, 'count') else len(response.data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch meal plans: {str(e)}"
        )


@router.get(
    "/{user_id}/meal-plans/details",
    status_code=status.HTTP_200_OK,
    summary="Get user meal plan details",
    description=    """
    Fetch user's meal plan with hierarchical structure:
    - Date level: Grouped by date
    - Meal type level: Grouped by meal type within each date
    - Meal items: List of meal items for each meal type
    - Grocery items: Each meal item includes grocery items grouped by their type
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Query Parameters:**
    - user_meal_plan_id (optional): ID of the specific meal plan to fetch. If not provided, returns all active meal plans.
    - is_active (optional): Filter by active status (true/false). Defaults to true if not specified.
    - limit (optional): Maximum number of meal plans to return when user_meal_plan_id is not provided (default: 50, max: 100).
    - max_dates (optional): Maximum number of dates to return across all meal plans (default: 500, max: 1000). Helps prevent very large responses.
    
    **Response Structure (Single Meal Plan):**
    ```json
    {
      "success": true,
      "dates": [
        {
          "date": "2024-01-01",
          "meals": [
            {
              "id": 1,
              "name": "Breakfast",
              "description": "...",
              "meal_items": [
                {
                  "id": 1,
                  "name": "Idli",
                  "description": "...",
                  "user_meal_plan_detail_id": 123,
                  "grocery_items_by_type": {
                    "Grains, Cereals & Grain Products": ["Rice", "Urad Dal"],
                    "Spices & Condiments": ["Salt"],
                    "Vegetables": ["Curry Leaves"]
                  },
                  ...
                }
              ]
            }
          ]
        }
      ]
    }
    ```
    
    **Note:** 
    - Each meal item includes `user_meal_plan_detail_id` which is the ID from the `user_meal_plan_details` table. This ID can be used for operations like swapping or removing meal items.
    - Each meal item includes `grocery_items_by_type` which contains the ingredient names grouped by their type.
    
    **Response Structure (Multiple Meal Plans):**
    ```json
    {
      "success": true,
      "dates": [
        {
          "date": "2024-01-01",
          "meals": [
            {
              "id": 1,
              "name": "Breakfast",
              "meal_items": [
                {
                  "id": 1,
                  "name": "Idli",
                  "user_meal_plan_detail_id": 123,
                  "grocery_items_by_type": {
                    "Grains, Cereals & Grain Products": ["Rice", "Urad Dal"]
                  },
                  ...
                }
              ]
            }
          ]
        },
        {
          "date": "2024-01-08",
          "meals": [...]
        }
      ]
    }
    ```
    
    **Note:** 
    - When multiple meal plans are returned, all dates from all meal plans are combined into a single `dates` array, sorted by date. 
    - Each meal item includes `user_meal_plan_detail_id` which is the ID from the `user_meal_plan_details` table.
    - Each meal item includes `grocery_items_by_type` which contains the ingredient names grouped by their type.
    
    Only returns active meal plan details (where is_active = true).
    If no user_meal_plan_id is provided, returns all active meal plans (up to limit).
    """
)
async def get_user_meal_plan(
    user_id: str = Depends(verify_user_access),
    user_meal_plan_id: Optional[int] = Query(None, description="ID of the user meal plan. If not provided, returns all active meal plans.", gt=0),
    is_active: Optional[bool] = Query(True, description="Filter by active status (only used when user_meal_plan_id is not provided)"),
    limit: int = Query(50, description="Maximum number of meal plans to return when user_meal_plan_id is not provided", ge=1, le=100),
    max_dates: int = Query(500, description="Maximum number of dates to return across all meal plans (helps prevent very large responses)", ge=1, le=1000)
) -> Dict[str, Any]:
    """
    Get user meal plan(s) with hierarchical structure.
    
    If user_meal_plan_id is provided, returns that specific meal plan.
    If not provided, returns all active meal plans (up to limit).
    
    Returns:
        Dict containing plan information and hierarchical meal plan details.
        Structure differs based on whether single or multiple plans are returned.
    """
    supabase = get_supabase_admin()
    
    try:
        # If user_meal_plan_id is provided, return single meal plan
        if user_meal_plan_id is not None:
            # Verify meal plan exists and belongs to user
            plan_response = supabase.table("user_meal_plan") \
                .select("id") \
                .eq("id", user_meal_plan_id) \
                .eq("user_id", user_id) \
                .execute()
            
            if not plan_response.data or len(plan_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Meal plan with id {user_meal_plan_id} not found or does not belong to you"
                )
            
            # Get meal plan details with joins to meal_types and meal_items
            details_response = supabase.table("user_meal_plan_details") \
                .select("""
                    id,
                    date,
                    is_active,
                    meal_type_id,
                    meal_item_id,
                    meal_types (
                        id,
                        name,
                        description,
                        is_active,
                        created_at
                    ),
                    meal_items (
                        id,
                        name,
                        description,
                        image_url,
                        can_vegetarian_eat,
                        can_eggetarian_eat,
                        can_carnitarian_eat,
                        can_omnitarian_eat,
                        can_vegan_eat,
                        is_breakfast,
                        is_lunch,
                        is_snacks,
                        is_dinner,
                        recipe_link,
                        created_at
                    )
                """) \
                .eq("user_meal_plan_id", user_meal_plan_id) \
                .eq("is_active", True) \
                .order("date") \
                .order("meal_type_id") \
                .execute()
            
            # Structure the data hierarchically using helper function
            dates_list = _structure_meal_plan_details(details_response.data)
            
            # Fetch grocery items for all meal items
            meal_item_ids = []
            for date_entry in dates_list:
                for meal in date_entry.get("meals", []):
                    for meal_item in meal.get("meal_items", []):
                        meal_item_id = meal_item.get("id")
                        if meal_item_id:
                            meal_item_ids.append(meal_item_id)
            
            # Fetch grocery items if there are meal items
            if meal_item_ids:
                grocery_items_map = await _fetch_grocery_items_for_meal_items(meal_item_ids)
                
                # Enrich each meal item with grocery items
                for date_entry in dates_list:
                    for meal in date_entry.get("meals", []):
                        for meal_item in meal.get("meal_items", []):
                            meal_item_id = meal_item.get("id")
                            if meal_item_id and meal_item_id in grocery_items_map:
                                meal_item["grocery_items_by_type"] = grocery_items_map[meal_item_id]
                            else:
                                meal_item["grocery_items_by_type"] = {}
            
            return {
                "success": True,
                "dates": dates_list,
                "total_dates": len(dates_list)
            }
        
        # If user_meal_plan_id is not provided, return all meal plans for user
        else:
            # Get all active meal plans for this user
            plans_query = supabase.table("user_meal_plan") \
                .select("id") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit)
            
            if is_active is not None:
                plans_query = plans_query.eq("is_active", is_active)
            
            plans_response = plans_query.execute()
            
            if not plans_response.data or len(plans_response.data) == 0:
                return {
                    "success": True,
                    "count": 0,
                    "data": []
                }
            
            # Get details for all meal plans and combine them
            all_details_data = []
            for plan in plans_response.data:
                plan_id = plan.get("id")
                
                # Get meal plan details with joins
                details_response = supabase.table("user_meal_plan_details") \
                    .select("""
                        id,
                        date,
                        is_active,
                        meal_type_id,
                        meal_item_id,
                        meal_types (
                            id,
                            name,
                            description,
                            is_active,
                            created_at
                        ),
                        meal_items (
                            id,
                            name,
                            description,
                            image_url,
                            can_vegetarian_eat,
                            can_eggetarian_eat,
                            can_carnitarian_eat,
                            can_omnitarian_eat,
                            can_vegan_eat,
                            is_breakfast,
                            is_lunch,
                            is_snacks,
                            is_dinner,
                            recipe_link,
                            created_at
                        )
                    """) \
                    .eq("user_meal_plan_id", plan_id) \
                    .eq("is_active", True) \
                    .execute()
                
                # Combine all details from all meal plans
                all_details_data.extend(details_response.data)
            
            # Structure all dates hierarchically (combines dates from all meal plans)
            all_dates_list = _structure_meal_plan_details(all_details_data)
            
            # Apply max_dates limit if specified
            if len(all_dates_list) > max_dates:
                all_dates_list = all_dates_list[:max_dates]
            
            # Fetch grocery items for all meal items
            meal_item_ids = []
            for date_entry in all_dates_list:
                for meal in date_entry.get("meals", []):
                    for meal_item in meal.get("meal_items", []):
                        meal_item_id = meal_item.get("id")
                        if meal_item_id:
                            meal_item_ids.append(meal_item_id)
            
            # Fetch grocery items if there are meal items
            if meal_item_ids:
                grocery_items_map = await _fetch_grocery_items_for_meal_items(meal_item_ids)
                
                # Enrich each meal item with grocery items
                for date_entry in all_dates_list:
                    for meal in date_entry.get("meals", []):
                        for meal_item in meal.get("meal_items", []):
                            meal_item_id = meal_item.get("id")
                            if meal_item_id and meal_item_id in grocery_items_map:
                                meal_item["grocery_items_by_type"] = grocery_items_map[meal_item_id]
                            else:
                                meal_item["grocery_items_by_type"] = {}
            
            return {
                "success": True,
                "dates": all_dates_list,
                "total_dates": len(all_dates_list),
                "limit_applied": len(all_dates_list) >= max_dates if user_meal_plan_id is None else False
            }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the error in production (you might want to add logging here)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch meal plan: {str(e)}"
        )


@router.get(
    "/{user_id}/meal-plans/bulk",
    status_code=status.HTTP_200_OK,
    summary="[DEPRECATED] Get multiple meal plans with full details",
    description="""
    **⚠️ DEPRECATED:** This endpoint is deprecated and will be removed in a future version.
    Use `/user/{user_id}/meal-plans/details` instead with the `user_meal_plan_id` query parameter
    or omit it to get all active meal plans.
    
    Fetch multiple meal plans with their full hierarchical details.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Query Parameters:**
    - plan_ids: Comma-separated list of meal plan IDs (e.g., "1,2,3")
    - is_active: Filter by active status (true/false) - only used if plan_ids not provided
    - limit: Maximum number of plans to return (default: 10, max: 50) - only used if plan_ids not provided
    
    **Response Structure:**
    ```json
    {
      "success": true,
      "data": [
        {
          "dates": [
            {
              "date": "2024-01-01",
              "meals": [...]
            }
          ]
        }
      ],
      "count": 1
    }
    ```
    
    **Note:** If plan_ids is provided, it takes precedence over is_active and limit filters.
    """
)
async def get_multiple_user_meal_plans(
    user_id: str = Depends(verify_user_access),
    plan_ids: Optional[str] = Query(None, description="Comma-separated list of meal plan IDs (e.g., '1,2,3')"),
    is_active: Optional[bool] = Query(None, description="Filter by active status (only if plan_ids not provided)"),
    limit: int = Query(10, description="Maximum number of plans to return (only if plan_ids not provided)", ge=1, le=50),
    response: Response = None
) -> Dict[str, Any]:
    """
    [DEPRECATED] Get multiple meal plans with full hierarchical details.
    
    This endpoint is deprecated. Use GET /user/{user_id}/meal-plans/details instead.
    
    Returns:
        Dict containing success status and list of meal plans with full details.
    """
    supabase = get_supabase_admin()
    
    # Add deprecation headers
    if response:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2025-12-31"
        response.headers["Link"] = '</user/{user_id}/meal-plans/details>; rel="successor-version"'
    
    try:
        # Parse plan IDs if provided
        plan_id_list = None
        if plan_ids:
            try:
                plan_id_list = [int(id.strip()) for id in plan_ids.split(",") if id.strip()]
                if not plan_id_list:
                    raise ValueError("No valid plan IDs provided")
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid plan_ids format: {str(e)}. Expected comma-separated integers."
                )
        
        # Get meal plans
        if plan_id_list:
            # Fetch specific plans that belong to user
            plans_query = supabase.table("user_meal_plan") \
                .select("*") \
                .eq("user_id", user_id) \
                .in_("id", plan_id_list)
        else:
            # Fetch plans with filters for this user
            plans_query = supabase.table("user_meal_plan") \
                .select("*") \
                .eq("user_id", user_id)
            
            if is_active is not None:
                plans_query = plans_query.eq("is_active", is_active)
            
            plans_query = plans_query.order("created_at", desc=True) \
                .limit(limit)
        
        plans_response = plans_query.execute()
        
        if not plans_response.data:
            return {
                "success": True,
                "data": [],
                "count": 0
            }
        
        # Get full details for each plan
        plans_with_details = []
        for plan in plans_response.data:
            plan_id = plan.get("id")
            
            # Get meal plan details with joins
            details_response = supabase.table("user_meal_plan_details") \
                .select("""
                    id,
                    date,
                    is_active,
                    meal_type_id,
                    meal_item_id,
                    meal_types (
                        id,
                        name,
                        description,
                        is_active,
                        created_at
                    ),
                    meal_items (
                        id,
                        name,
                        description,
                        image_url,
                        can_vegetarian_eat,
                        can_eggetarian_eat,
                        can_carnitarian_eat,
                        can_omnitarian_eat,
                        can_vegan_eat,
                        is_breakfast,
                        is_lunch,
                        is_snacks,
                        is_dinner,
                        recipe_link,
                        created_at
                    )
                """) \
                .eq("user_meal_plan_id", plan_id) \
                .eq("is_active", True) \
                .order("date") \
                .order("meal_type_id") \
                .execute()
            
            # Structure the data hierarchically
            dates_list = _structure_meal_plan_details(details_response.data)
            
            # Fetch grocery items for all meal items in this plan
            meal_item_ids = []
            for date_entry in dates_list:
                for meal in date_entry.get("meals", []):
                    for meal_item in meal.get("meal_items", []):
                        meal_item_id = meal_item.get("id")
                        if meal_item_id:
                            meal_item_ids.append(meal_item_id)
            
            # Fetch grocery items if there are meal items
            if meal_item_ids:
                grocery_items_map = await _fetch_grocery_items_for_meal_items(meal_item_ids)
                
                # Enrich each meal item with grocery items
                for date_entry in dates_list:
                    for meal in date_entry.get("meals", []):
                        for meal_item in meal.get("meal_items", []):
                            meal_item_id = meal_item.get("id")
                            if meal_item_id and meal_item_id in grocery_items_map:
                                meal_item["grocery_items_by_type"] = grocery_items_map[meal_item_id]
                            else:
                                meal_item["grocery_items_by_type"] = {}
            
            plans_with_details.append({
                "dates": dates_list
            })
        
        return {
            "success": True,
            "data": plans_with_details,
            "count": len(plans_with_details),
            "deprecation_warning": "This endpoint is deprecated. Use GET /user/{user_id}/meal-plans/details instead."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch meal plans: {str(e)}"
        )


@router.put(
    "/{user_id}/meal-plans/swap-item",
    status_code=status.HTTP_200_OK,
    summary="Swap a meal item in meal plan",
    description="""
    Swap a meal item in the user's meal plan.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **How it works:**
    1. Finds the existing meal plan detail record by `user_meal_plan_detail_id`
    2. Sets `is_active = false` on the existing record
    3. Creates a new record with:
       - Same `date`
       - Same `user_meal_plan_id`
       - Same `meal_type_id`
       - New `meal_item_id`
       - `is_active = true`
    
    **Request Body:**
    ```json
    {
      "user_meal_plan_detail_id": 123,
      "new_meal_item_id": 45
    }
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "message": "Meal item swapped successfully",
      "data": {
        "old_detail_id": 123,
        "new_detail_id": 456,
        "date": "2024-01-01",
        "meal_type_id": 1,
        "old_meal_item_id": 10,
        "new_meal_item_id": 45
      }
    }
    ```
    """
)
async def swap_meal_item(
    request: SwapMealItemRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Swap a meal item in the meal plan.
    
    Returns:
        Dict containing success status and swap details.
    """
    supabase = get_supabase_admin()
    
    try:
        # Get the existing meal plan detail record
        existing_detail_response = supabase.table("user_meal_plan_details") \
            .select("*") \
            .eq("id", request.user_meal_plan_detail_id) \
            .eq("is_active", True) \
            .execute()
        
        if not existing_detail_response.data or len(existing_detail_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active meal plan detail with id {request.user_meal_plan_detail_id} not found"
            )
        
        existing_detail = existing_detail_response.data[0]
        
        # Get the required fields from existing record
        date = existing_detail.get("date")
        user_meal_plan_id = existing_detail.get("user_meal_plan_id")
        meal_type_id = existing_detail.get("meal_type_id")
        old_meal_item_id = existing_detail.get("meal_item_id")
        
        if not all([date, user_meal_plan_id, meal_type_id]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Existing meal plan detail is missing required fields"
            )
        
        # Verify the meal plan belongs to the user
        plan_ownership_check = supabase.table("user_meal_plan") \
            .select("id") \
            .eq("id", user_meal_plan_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if not plan_ownership_check.data or len(plan_ownership_check.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to modify this meal plan"
            )
        
        # Verify the new meal item exists
        meal_item_response = supabase.table("meal_items") \
            .select("id") \
            .eq("id", request.new_meal_item_id) \
            .eq("is_active", True) \
            .execute()
        
        if not meal_item_response.data or len(meal_item_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active meal item with id {request.new_meal_item_id} not found"
            )
        
        # Set is_active = false on existing record
        update_response = supabase.table("user_meal_plan_details") \
            .update({"is_active": False}) \
            .eq("id", request.user_meal_plan_detail_id) \
            .execute()
        
        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate existing meal plan detail"
            )
        
        # Create new record with new meal_item_id
        new_detail_data = {
            "user_meal_plan_id": user_meal_plan_id,
            "date": date,
            "meal_type_id": meal_type_id,
            "meal_item_id": request.new_meal_item_id,
            "is_active": True
        }
        
        new_detail_response = supabase.table("user_meal_plan_details") \
            .insert(new_detail_data) \
            .execute()
        
        if not new_detail_response.data or len(new_detail_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create new meal plan detail"
            )
        
        new_detail = new_detail_response.data[0]
        
        return {
            "success": True,
            "message": "Meal item swapped successfully",
            "data": {
                "old_detail_id": request.user_meal_plan_detail_id,
                "new_detail_id": new_detail.get("id"),
                "date": date,
                "meal_type_id": meal_type_id,
                "old_meal_item_id": old_meal_item_id,
                "new_meal_item_id": request.new_meal_item_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to swap meal item: {str(e)}"
        )


@router.post(
    "/{user_id}/meal-plans/add-item",
    status_code=status.HTTP_201_CREATED,
    summary="Add a meal item to meal plan",
    description="""
    Add a new meal item to the user's meal plan for a specific date and meal type.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Request Body:**
    ```json
    {
      "user_meal_plan_id": 1,
      "date": "2024-01-01",
      "meal_type_id": 1,
      "meal_item_id": 45
    }
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "message": "Meal item added successfully",
      "data": {
        "id": 456,
        "user_meal_plan_id": 1,
        "date": "2024-01-01",
        "meal_type_id": 1,
        "meal_item_id": 45,
        "is_active": true
      }
    }
    ```
    """
)
async def add_meal_item(
    request: AddMealItemRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Add a meal item to the meal plan.
    
    Returns:
        Dict containing success status and the created meal plan detail.
    """
    supabase = get_supabase_admin()
    
    try:
        # Verify the meal plan exists and belongs to user
        plan_response = supabase.table("user_meal_plan") \
            .select("id") \
            .eq("id", request.user_meal_plan_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if not plan_response.data or len(plan_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal plan with id {request.user_meal_plan_id} not found or does not belong to you"
            )
        
        # Verify the meal type exists
        meal_type_response = supabase.table("meal_types") \
            .select("id") \
            .eq("id", request.meal_type_id) \
            .eq("is_active", True) \
            .execute()
        
        if not meal_type_response.data or len(meal_type_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active meal type with id {request.meal_type_id} not found"
            )
        
        # Verify the meal item exists
        meal_item_response = supabase.table("meal_items") \
            .select("id") \
            .eq("id", request.meal_item_id) \
            .eq("is_active", True) \
            .execute()
        
        if not meal_item_response.data or len(meal_item_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active meal item with id {request.meal_item_id} not found"
            )
        
        # Create new record
        new_detail_data = {
            "user_meal_plan_id": request.user_meal_plan_id,
            "date": request.date,
            "meal_type_id": request.meal_type_id,
            "meal_item_id": request.meal_item_id,
            "is_active": True
        }
        
        new_detail_response = supabase.table("user_meal_plan_details") \
            .insert(new_detail_data) \
            .execute()
        
        if not new_detail_response.data or len(new_detail_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add meal item to meal plan"
            )
        
        new_detail = new_detail_response.data[0]
        
        return {
            "success": True,
            "message": "Meal item added successfully",
            "data": new_detail
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add meal item: {str(e)}"
        )


@router.delete(
    "/{user_id}/meal-plans/remove-item",
    status_code=status.HTTP_200_OK,
    summary="Remove a meal item from meal plan",
    description="""
    Remove a meal item from the user's meal plan by setting is_active = false.
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Request Body:**
    ```json
    {
      "user_meal_plan_detail_id": 123
    }
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "message": "Meal item removed successfully",
      "data": {
        "user_meal_plan_detail_id": 123,
        "is_active": false
      }
    }
    ```
    """
)
async def remove_meal_item(
    request: RemoveMealItemRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Remove a meal item from the meal plan.
    
    Returns:
        Dict containing success status and removal details.
    """
    supabase = get_supabase_admin()
    
    try:
        # Get the existing meal plan detail record
        existing_detail_response = supabase.table("user_meal_plan_details") \
            .select("*") \
            .eq("id", request.user_meal_plan_detail_id) \
            .eq("is_active", True) \
            .execute()
        
        if not existing_detail_response.data or len(existing_detail_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active meal plan detail with id {request.user_meal_plan_detail_id} not found"
            )
        
        existing_detail = existing_detail_response.data[0]
        user_meal_plan_id = existing_detail.get("user_meal_plan_id")
        
        # Verify the meal plan belongs to the user
        if user_meal_plan_id:
            plan_ownership_check = supabase.table("user_meal_plan") \
                .select("id") \
                .eq("id", user_meal_plan_id) \
                .eq("user_id", user_id) \
                .execute()
            
            if not plan_ownership_check.data or len(plan_ownership_check.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to modify this meal plan"
                )
        
        # Set is_active = false
        update_response = supabase.table("user_meal_plan_details") \
            .update({"is_active": False}) \
            .eq("id", request.user_meal_plan_detail_id) \
            .execute()
        
        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove meal item from meal plan"
            )
        
        return {
            "success": True,
            "message": "Meal item removed successfully",
            "data": {
                "user_meal_plan_detail_id": request.user_meal_plan_detail_id,
                "is_active": False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove meal item: {str(e)}"
        )

