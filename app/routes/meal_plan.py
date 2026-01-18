# app/routes/meal_plan.py

from fastapi import APIRouter, HTTPException, status, Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.services.meal_generation_service import meal_generation_service
from app.services.supabase_client import get_supabase_admin

router = APIRouter(prefix="/meal-plan", tags=["Meal Plan Generation"])


class GenerateMealPlanRequest(BaseModel):
    """Request to generate and store a meal plan"""
    start_date: Optional[str] = Field(
        None, 
        description="Start date in YYYY-MM-DD format. Defaults to today if not provided"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2024-01-15"
            }
        }


@router.post(
    "/generate/{user_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Generate and store meal plan for user",
    description="""
    Generate a 7-day meal plan for a specific user using AI and store it in the database.
    
    This endpoint:
    1. Takes user_id as a path parameter
    2. Fetches user preferences using meal_generation_service
    3. Generates a meal plan using OpenAI
    4. Creates a user_meal_plan record in the database
    5. Creates user_meal_plan_details records for all meals
    
    **Request Body:**
    ```json
    {
      "start_date": "2024-01-15"  // Optional, defaults to today
    }
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "message": "Meal plan generated and stored successfully",
      "data": {
        "user_meal_plan_id": 1,
        "start_date": "2024-01-15",
        "end_date": "2024-01-21",
        "total_meals": 28,
        "total_days": 7
      }
    }
    ```
    """
)
async def generate_and_store_meal_plan(
    user_id: str = Path(..., description="User ID for meal plan generation"),
    request: GenerateMealPlanRequest = GenerateMealPlanRequest()
) -> Dict[str, Any]:
    """
    Generate a meal plan and store it in the database.
    """
    supabase = get_supabase_admin()
    
    try:
        # Parse start date
        if request.start_date:
            try:
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        else:
            start_date = datetime.now().date()
        
        # Calculate end date (7 days from start)
        end_date = start_date + timedelta(days=6)
        
        # Check if a meal plan already exists for this user and date range
        existing_plan_response = supabase.table("user_meal_plan") \
            .select("id, start_date, end_date") \
            .eq("user_id", user_id) \
            .eq("start_date", start_date.isoformat()) \
            .eq("end_date", end_date.isoformat()) \
            .execute()
        
        if existing_plan_response.data and len(existing_plan_response.data) > 0:
            existing_plan = existing_plan_response.data[0]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A meal plan already exists for this user from {start_date.isoformat()} to {end_date.isoformat()}. Meal plan ID: {existing_plan.get('id')}"
            )
        
        # Generate meal plan using the service
        meal_plan_data = await meal_generation_service.generate_meal_plan(
            user_id=user_id,
            start_date=datetime.combine(start_date, datetime.min.time())
        )
        
        # Validate meal plan structure
        if "meal_plan" not in meal_plan_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid meal plan format from generation service"
            )
        
        # Get meal type mappings (breakfast, lunch, snacks, dinner -> meal_type_id)
        meal_type_mapping = await _get_meal_type_mapping(supabase)
        
        # Create user_meal_plan record
        meal_plan_record = {
            "user_id": user_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "is_active": True
        }
        
        plan_response = supabase.table("user_meal_plan") \
            .insert(meal_plan_record) \
            .execute()
        
        if not plan_response.data or len(plan_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create meal plan record"
            )
        
        user_meal_plan_id = plan_response.data[0]["id"]
        
        # Prepare meal plan details to insert
        # Note: user_meal_plan_id, meal_type_id, and meal_item_id are smallint in the schema
        meal_plan_details = []
        total_meals = 0
        
        for day_plan in meal_plan_data.get("meal_plan", []):
            date_str = day_plan.get("date")
            meals = day_plan.get("meals", {})
            
            # Process each meal type
            for meal_type_name, meal_items in meals.items():
                if not meal_items:
                    continue
                
                # Get meal_type_id from mapping
                meal_type_id = meal_type_mapping.get(meal_type_name.lower())
                if not meal_type_id:
                    # Skip if meal type not found
                    print(f"Warning: Meal type '{meal_type_name}' not found in mapping")
                    continue
                
                # Create a detail record for each meal item
                for meal_item in meal_items:
                    meal_item_id = meal_item.get("id")
                    if not meal_item_id:
                        continue
                    
                    # Ensure IDs are within smallint range (though Supabase should handle this)
                    # smallint range: -32768 to 32767
                    meal_plan_details.append({
                        "user_meal_plan_id": int(user_meal_plan_id),
                        "date": date_str,
                        "meal_type_id": int(meal_type_id),
                        "meal_item_id": int(meal_item_id),
                        "is_active": True
                    })
                    total_meals += 1
        
        # Bulk insert meal plan details
        if meal_plan_details:
            details_response = supabase.table("user_meal_plan_details") \
                .insert(meal_plan_details) \
                .execute()
            
            if not details_response.data:
                # Rollback: delete the meal plan if details insertion failed
                supabase.table("user_meal_plan") \
                    .delete() \
                    .eq("id", user_meal_plan_id) \
                    .execute()
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create meal plan details"
                )
        
        return {
            "success": True,
            "message": "Meal plan generated and stored successfully",
            "data": {
                "user_meal_plan_id": user_meal_plan_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_meals": total_meals,
                "total_days": 7
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate and store meal plan: {str(e)}"
        )


async def _get_meal_type_mapping(supabase) -> Dict[str, int]:
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
        # Check for common variations
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
        # Fallback to common defaults if table doesn't exist or query fails
        print(f"Warning: Could not fetch meal types from database: {e}")
        return {
            "breakfast": 1,
            "lunch": 2,
            "snacks": 3,
            "dinner": 4
        }
