# app/routes/meal_messaging.py

from fastapi import APIRouter, HTTPException, status, Query, Path
from app.services.meal_messaging_service import meal_messaging_service
from typing import Dict, Any, Optional
from datetime import date

router = APIRouter(prefix="/meal-messaging", tags=["Meal Messaging"])


@router.get(
    "/{user_id}/today",
    status_code=status.HTTP_200_OK,
    summary="Get today's meal messages for user and cook",
    description="""
    Generate meal messages in English and cook's language for today's meals.
    
    This endpoint:
    1. Fetches today's meal plan for the user
    2. Gets the cook's language (first language from languages_known)
    3. Generates messages in English and cook's language
    4. Uses Google Translate API if cook's language is not English
    
    **Query Parameters:**
    - cook_id (optional): Specific cook ID to use. If not provided, uses the first cook.
    - date (optional): Date in YYYY-MM-DD format. Defaults to today.
    - meal_type_id (optional): Filter by specific meal type ID (e.g., 1 for breakfast). If not provided, returns all meal types.
    
    **Response:**
    ```json
    {
      "success": true,
      "date": "2024-01-15",
      "cook": {
        "id": "uuid",
        "name": "Ramesh Kumar",
        "language": "hi",
        "languages_known": ["Hindi", "English"]
      },
      "messages": {
        "english": "Today's Breakfast is Moong Dal Cheela\\nToday's Lunch is...",
        "cook_language": "आज का नाश्ता मूंग दाल चीला है\\nआज का दोपहर का भोजन...",
        "cook_language_code": "hi"
      },
      "meals": {
        "breakfast": ["Moong Dal Cheela"],
        "lunch": ["Steamed Rice", "Dal", "Sabji"],
        "snacks": ["Fruits"],
        "dinner": ["Roti", "Dal", "Sabji"]
      }
    }
    ```
    """
)
async def get_today_meal_messages(
    user_id: str = Path(..., description="User ID"),
    cook_id: Optional[str] = Query(None, description="Specific cook ID to use. If not provided, uses the first cook."),
    date_str: Optional[str] = Query(None, description="Date in YYYY-MM-DD format. Defaults to today.", alias="date"),
    meal_type_id: Optional[int] = Query(None, description="Filter by specific meal type ID (e.g., 1 for breakfast). If not provided, returns all meal types.", gt=0)
) -> Dict[str, Any]:
    """
    Get today's meal messages in English and cook's language.
    """
    try:
        # Parse date if provided
        parsed_date = None
        if date_str:
            try:
                parsed_date = date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        
        # Generate messages
        result = await meal_messaging_service.generate_meal_messages(
            user_id=user_id,
            cook_id=cook_id,
            target_date=parsed_date,
            meal_type_id=meal_type_id
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("message", "Failed to generate meal messages")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_today_meal_messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate meal messages: {str(e)}"
        )
