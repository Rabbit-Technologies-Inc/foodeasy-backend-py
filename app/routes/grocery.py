"""
Grocery Routes

Routes for fetching ingredients (groceries) required for a user's meal plan.
Uses meal_item_ingredients junction table to link meal items to meal_ingredients.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from app.services.supabase_client import get_supabase_admin
from app.dependencies.auth import verify_user_access
from typing import Dict, Any
from collections import defaultdict

router = APIRouter(prefix="/grocery", tags=["Grocery"])


@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Get ingredients for user's recent meal plan",
    description="""
    Get all ingredients (groceries) with their types required for a user's most recent meal plan.
    
    This endpoint:
    1. Fetches the user's most recent active meal plan (based on user_id and the highest meal plan id)
    2. Gets all meal items from that meal plan
    3. Fetches all ingredients required for those meal items via meal_item_ingredients junction table
    4. Groups ingredients by their types
    
    **Authentication Required:** Bearer token in Authorization header.
    
    **Response Structure:**
    ```json
    {
      "success": true,
      "data": {
        "meal_plan_id": 1,
        "start_date": "2024-01-15",
        "end_date": "2024-01-21",
        "grocery_items_by_type": {
          "Grains, Cereals & Grain Products": ["Rice", "Wheat Flour"],
          "Vegetables": ["Tomato", "Onion", "Potato"],
          "Cooking Oils & Fats": ["Mustard Oil"]
        }
      }
    }
    ```
    
    If no meal plan exists for the user, returns an empty list.
    """
)
async def get_user_groceries(
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Get all ingredients (groceries) with their types required for a user's most recent meal plan.
    
    Returns:
        Dict containing success status, meal plan info, and ingredients grouped by type.
    """
    supabase = get_supabase_admin()
    
    try:
        # Get the most recent meal plan for the user
        # Order by id DESC (assuming id is auto-incrementing) or created_at DESC
        meal_plan_response = supabase.table("user_meal_plan") \
            .select("id, start_date, end_date, created_at") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .order("id", desc=True) \
            .limit(1) \
            .execute()
        
        if not meal_plan_response.data or len(meal_plan_response.data) == 0:
            return {
                "success": True,
                "data": {
                    "meal_plan_id": None,
                    "start_date": None,
                    "end_date": None,
                    "grocery_items_by_type": {}
                },
                "message": "No active meal plan found for this user"
            }
        
        meal_plan = meal_plan_response.data[0]
        meal_plan_id = meal_plan["id"]
        
        # Get all meal items from the meal plan details
        meal_plan_details_response = supabase.table("user_meal_plan_details") \
            .select("meal_item_id") \
            .eq("user_meal_plan_id", meal_plan_id) \
            .eq("is_active", True) \
            .execute()
        
        if not meal_plan_details_response.data:
            return {
                "success": True,
                "data": {
                    "meal_plan_id": meal_plan_id,
                    "start_date": meal_plan.get("start_date"),
                    "end_date": meal_plan.get("end_date"),
                    "grocery_items_by_type": {}
                },
                "message": "No meal items found in the meal plan"
            }
        
        # Extract unique meal item IDs
        meal_item_ids = list(set([
            detail["meal_item_id"] for detail in meal_plan_details_response.data
        ]))
        
        # If no meal item IDs, return empty result
        if not meal_item_ids:
            return {
                "success": True,
                "data": {
                    "meal_plan_id": meal_plan_id,
                    "start_date": meal_plan.get("start_date"),
                    "end_date": meal_plan.get("end_date"),
                    "grocery_items_by_type": {}
                },
                "message": "No meal items found in the meal plan"
            }
        
        # Fetch ingredients for these meal items using the correct schema
        # Schema: meal_item_ingredients (junction) -> meal_ingredients -> meal_ingredients_types
        
        try:
            # Query the junction table with joins to get ingredient details
            ingredients_response = supabase.table("meal_item_ingredients") \
                .select("""
                    id,
                    meal_item_id,
                    meal_ingredient_id,
                    quantity,
                    unit,
                    meal_ingredients (
                        id,
                        name,
                        description,
                        meal_ingredient_type_id,
                        meal_ingredients_types (
                            id,
                            name
                        )
                    )
                """) \
                .in_("meal_item_id", meal_item_ids) \
                .eq("is_active", True) \
                .execute()
            
            # Process the results and group by ingredient
            grocery_item_map = {}
            
            if ingredients_response.data:
                for item in ingredients_response.data:
                    ingredient_data = item.get("meal_ingredients")
                    if not ingredient_data:
                        continue
                    
                    ingredient_id = ingredient_data.get("id")
                    meal_item_id = item.get("meal_item_id")
                    
                    if ingredient_id not in grocery_item_map:
                        ingredient_type_data = ingredient_data.get("meal_ingredients_types")
                        
                        # Format quantity with unit
                        quantity = item.get("quantity")
                        unit = item.get("unit")
                        quantity_str = ""
                        if quantity:
                            quantity_str = str(quantity)
                            if unit:
                                quantity_str += f" {unit}"
                        
                        grocery_item_map[ingredient_id] = {
                            "id": ingredient_id,
                            "name": ingredient_data.get("name"),
                            "type": ingredient_type_data.get("name") if ingredient_type_data else "Uncategorized",
                            "type_id": ingredient_data.get("meal_ingredient_type_id"),
                            "quantity": quantity_str or None,
                            "description": ingredient_data.get("description"),
                            "meal_items": []
                        }
                    
                    # Add meal item to the list
                    if meal_item_id and meal_item_id not in grocery_item_map[ingredient_id]["meal_items"]:
                        grocery_item_map[ingredient_id]["meal_items"].append(meal_item_id)
                
                grocery_items = list(grocery_item_map.values())
            else:
                grocery_items = []
        
        except Exception as e:
            print(f"Error fetching ingredients: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch grocery items: {str(e)}"
            )
        
        # Group groceries by type (only ingredient names)
        grocery_items_by_type = defaultdict(list)
        for grocery in grocery_items:
            type_name = grocery.get("type") or "Uncategorized"
            ingredient_name = grocery.get("name")
            if ingredient_name and ingredient_name not in grocery_items_by_type[type_name]:
                grocery_items_by_type[type_name].append(ingredient_name)
        
        # Convert defaultdict to regular dict for JSON serialization
        grocery_items_by_type = dict(grocery_items_by_type)
        
        return {
            "success": True,
            "data": {
                "meal_plan_id": meal_plan_id,
                "start_date": meal_plan.get("start_date"),
                "end_date": meal_plan.get("end_date"),
                "grocery_items_by_type": grocery_items_by_type
            }
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the error in production (you might want to add logging here)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch grocery items: {str(e)}"
        )
