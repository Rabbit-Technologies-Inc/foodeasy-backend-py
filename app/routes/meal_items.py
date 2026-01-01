"""
Meal Items Routes

Routes for fetching meal items with various filters.
"""

from fastapi import APIRouter, HTTPException, status, Query
from app.services.supabase_client import get_supabase_admin
from typing import Dict, Any, Optional

router = APIRouter(prefix="/meal-items", tags=["Meal Items"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get active meal items with filters",
    description="""
    Get active meal items from the meal_items table with optional filters.
    
    **Filters available:**
    - can_vegetarian_eat: Filter by vegetarian compatibility (true/false)
    - can_eggetarian_eat: Filter by eggetarian compatibility (true/false)
    - can_carnitarian_eat: Filter by carnitarian compatibility (true/false)
    - can_omnitarian_eat: Filter by omnitarian compatibility (true/false)
    - can_vegan_eat: Filter by vegan compatibility (true/false)
    - is_breakfast: Filter by breakfast meal type (true/false)
    - is_lunch: Filter by lunch meal type (true/false)
    - is_dinner: Filter by dinner meal type (true/false)
    - is_snacks: Filter by snacks meal type (true/false)
    
    **Note:** All filters are optional. If no filters are provided, all active meal items are returned.
    Only returns items where is_active = true.
    Response excludes created_at and is_active fields.
    """
)
async def get_meal_items(
    can_vegetarian_eat: Optional[bool] = Query(None, description="Filter by vegetarian compatibility"),
    can_eggetarian_eat: Optional[bool] = Query(None, description="Filter by eggetarian compatibility"),
    can_carnitarian_eat: Optional[bool] = Query(None, description="Filter by carnitarian compatibility"),
    can_omnitarian_eat: Optional[bool] = Query(None, description="Filter by omnitarian compatibility"),
    can_vegan_eat: Optional[bool] = Query(None, description="Filter by vegan compatibility"),
    is_breakfast: Optional[bool] = Query(None, description="Filter by breakfast meal type"),
    is_lunch: Optional[bool] = Query(None, description="Filter by lunch meal type"),
    is_dinner: Optional[bool] = Query(None, description="Filter by dinner meal type"),
    is_snacks: Optional[bool] = Query(None, description="Filter by snacks meal type")
) -> Dict[str, Any]:
    """
    Get active meal items with optional filters.
    
    Returns:
        Dict containing success status and list of filtered meal items.
        Response excludes created_at and is_active fields.
    """
    supabase = get_supabase_admin()
    
    try:
        # Start with base query - only active items
        query = supabase.table("meal_items") \
            .select("*") \
            .eq("is_active", True)
        
        # Apply dietary pattern filters
        if can_vegetarian_eat is not None:
            query = query.eq("can_vegetarian_eat", can_vegetarian_eat)
        
        if can_eggetarian_eat is not None:
            query = query.eq("can_eggetarian_eat", can_eggetarian_eat)
        
        if can_carnitarian_eat is not None:
            query = query.eq("can_carnitarian_eat", can_carnitarian_eat)
        
        if can_omnitarian_eat is not None:
            query = query.eq("can_omnitarian_eat", can_omnitarian_eat)
        
        if can_vegan_eat is not None:
            query = query.eq("can_vegan_eat", can_vegan_eat)
        
        # Apply meal type filters (these are boolean fields in the table)
        if is_breakfast is not None:
            query = query.eq("is_breakfast", is_breakfast)
        
        if is_lunch is not None:
            query = query.eq("is_lunch", is_lunch)
        
        if is_dinner is not None:
            query = query.eq("is_dinner", is_dinner)
        
        if is_snacks is not None:
            query = query.eq("is_snacks", is_snacks)
        
        # Execute query
        response = query.order("id").execute()
        
        # Remove created_at and is_active from each item
        filtered_data = [
            {k: v for k, v in item.items() if k not in ["created_at", "is_active"]}
            for item in response.data
        ]
        
        return {
            "success": True,
            "data": filtered_data,
            "count": len(filtered_data)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the error in production (you might want to add logging here)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch meal items: {str(e)}"
        )

