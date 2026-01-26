# app/routes/test_meal_generation.py

from fastapi import APIRouter, HTTPException, status, Path, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path as PathLib
from app.services.meal_generation_service_2 import meal_generation_service
from app.services.supabase_client import get_supabase_admin

router = APIRouter(prefix="/test-meal-generation", tags=["Meal Generation Testing"])

# Setup templates - use absolute path relative to this file
template_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))


class TestMealGenerationRequest(BaseModel):
    """Request to test meal generation with custom prompts"""
    user_id: str = Field(..., description="User ID (UUID) to generate meal plan for")
    system_prompt_part: Optional[str] = Field(
        None, 
        description="Custom system prompt part 1 (dynamic rules). If not provided, uses default from service."
    )
    user_prompt_part1: Optional[str] = Field(
        None, 
        description="Custom user prompt part 1 (dynamic instructions). If not provided, uses default from service. Part 2 (user preferences) is always included automatically."
    )
    start_date: Optional[str] = Field(
        None, 
        description="Start date in YYYY-MM-DD format. Defaults to today if not provided"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "system_prompt": "You are an expert meal planner...",
                "user_prompt": "Generate a 7-day meal plan...",
                "start_date": "2024-01-15"
            }
        }


@router.get("/", response_class=HTMLResponse)
async def get_test_ui(request: Request):
    """Serve the meal generation testing UI"""
    try:
        # Get default prompts from service (if available)
        # For now, we'll use empty strings and let users fill them
        default_system_prompt = ""
        default_user_prompt = ""
        
        return templates.TemplateResponse(
            "test_meal_generation.html",
            {
                "request": request,
                "system_prompt": default_system_prompt,
                "user_prompt": default_user_prompt
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load UI: {str(e)}"
        )


@router.get(
    "/get-default-prompts/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Get default prompts for a user",
    description="""
    Get the default system prompt (Part 1) and user prompt for a user.
    This helps users see what the default prompts look like before customizing.
    """
)
async def get_default_prompts(
    user_id: str = Path(..., description="User ID (UUID)")
) -> Dict[str, Any]:
    """Get default prompts for display in the testing UI"""
    try:
        # Get user details
        user_details = await meal_generation_service.get_user_details_with_preferences(user_id)
        
        # Fetch meal items
        meal_items = meal_generation_service._fetch_all_meal_items()
        
        # Build default prompts (without custom parts)
        system_prompt = meal_generation_service._build_system_prompt(meal_items, None)
        user_prompt = meal_generation_service._build_user_prompt(user_details, datetime.now(), None)
        
        # Extract Part 1 (dynamic part) from system prompt
        # Part 1 ends before "AVAILABLE MEAL ITEMS:"
        system_prompt_parts = system_prompt.split("AVAILABLE MEAL ITEMS:")
        system_prompt_part1 = system_prompt_parts[0].strip() if len(system_prompt_parts) > 0 else system_prompt
        
        # Extract Part 1 (dynamic part) from user prompt
        # Part 1 ends before "USER PROFILE:"
        user_prompt_parts = user_prompt.split("USER PROFILE:")
        user_prompt_part1 = user_prompt_parts[0].strip() if len(user_prompt_parts) > 0 else user_prompt
        
        return {
            "success": True,
            "data": {
                "system_prompt_part1": system_prompt_part1,
                "user_prompt_part1": user_prompt_part1,
                "user_prompt_full": user_prompt  # Full prompt for reference
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch default prompts: {str(e)}"
        )


@router.get(
    "/fetch-preferences/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Fetch user preferences for testing",
    description="""
    Fetch user preferences and details for the testing UI.
    This endpoint is similar to the Django version's fetch-preferences endpoint.
    """
)
async def fetch_user_preferences(
    user_id: str = Path(..., description="User ID (UUID)")
) -> Dict[str, Any]:
    """Fetch user preferences for display in the testing UI"""
    try:
        # Get user details with preferences
        user_details = await meal_generation_service.get_user_details_with_preferences(user_id)
        
        # Format preferences for display
        preferences = {
            'age': user_details.get('age'),
            'gender': user_details.get('gender'),
            'goals': user_details.get('goals', []),
            'medical_restrictions': user_details.get('medical_restrictions', []),
            'dietary_restrictions': user_details.get('dietary_restrictions', []),
            'dietary_pattern': user_details.get('dietary_pattern'),
            'nutrition_preferences': user_details.get('nutrition_preferences', []),
            'spice_level': user_details.get('spice_level'),
            'cuisines_preferences': user_details.get('cuisines_preferences', []),
            'breakfast_preferences': user_details.get('breakfast_preferences', []),
            'lunch_preferences': user_details.get('lunch_preferences', []),
            'snacks_preferences': user_details.get('snacks_preferences', []),
            'dinner_preferences': user_details.get('dinner_preferences', []),
            'total_household_adults': user_details.get('total_household_adults'),
            'total_household_children': user_details.get('total_household_children'),
            'extra_input': user_details.get('extra_input'),
        }
        
        return {
            "success": True,
            "preferences": preferences
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch preferences: {str(e)}"
        )


@router.post(
    "/test-generate",
    status_code=status.HTTP_200_OK,
    summary="Test meal generation with optional custom prompts",
    description="""
    Test meal generation with optional custom system prompt part 1 and user prompt part 1.
    - If system_prompt_part is provided, it replaces the dynamic rules part (Part 1)
    - If user_prompt_part1 is provided, it replaces the dynamic instructions part (Part 1)
    - If not provided, uses default prompts from the service
    - Part 2 of system prompt (meal items JSON + output format) is always static
    - Part 2 of user prompt (user preferences) is always included automatically
    """
)
async def test_meal_generation(
    request: TestMealGenerationRequest
) -> Dict[str, Any]:
    """Test meal generation with optional custom prompts"""
    try:
        # Parse start date
        if request.start_date:
            try:
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        else:
            start_date = datetime.now()
        
        # Generate meal plan with optional custom prompts
        # Note: system_prompt_part is Part 1 (dynamic), Part 2 (static) is always included
        # Note: user_prompt_part1 is Part 1 (dynamic), Part 2 (user preferences) is always included
        meal_plan_data = await meal_generation_service.generate_meal_plan(
            user_id=request.user_id,
            start_date=start_date,
            custom_system_prompt_part=request.system_prompt_part,
            custom_user_prompt_part1=request.user_prompt_part1
        )
        
        return {
            "success": True,
            "message": "Meal plan generated successfully",
            "data": meal_plan_data
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate meal plan: {str(e)}"
        )


@router.get(
    "/list-users",
    status_code=status.HTTP_200_OK,
    summary="List all users with their profiles",
    description="""
    Fetch all users from the database with their complete profiles including metadata.
    This endpoint is for testing purposes to view all users and their preferences.
    """
)
async def list_all_users(
    limit: int = Query(100, description="Maximum number of users to return", ge=1, le=1000),
    offset: int = Query(0, description="Number of users to skip for pagination", ge=0)
) -> Dict[str, Any]:
    """List all users with their profiles"""
    try:
        supabase = get_supabase_admin()
        
        # Fetch users with pagination (only active users)
        result = supabase.table('user_profiles') \
            .select('*') \
            .eq('is_active', True) \
            .order('created_at', desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        
        # Format users with their profiles
        users = []
        for user in result.data:
            metadata = user.get('metadata', {})
            if not isinstance(metadata, dict):
                metadata = {}
            
            user_profile = {
                'id': user.get('id'),
                'firebase_uid': user.get('firebase_uid'),
                'phone_number': user.get('phone_number'),
                'full_name': user.get('full_name'),
                'created_at': user.get('created_at'),
                'last_login': user.get('last_login'),
                'profile': {
                    'age': metadata.get('age'),
                    'gender': metadata.get('gender'),
                    'total_household_adults': metadata.get('total_household_adults'),
                    'total_household_children': metadata.get('total_household_children'),
                    'onboarding_completed': metadata.get('onboarding_completed', False),
                    'onboarding_completed_at': metadata.get('onboarding_completed_at'),
                    'goals': metadata.get('goals', []),
                    'medical_restrictions': metadata.get('medical_restrictions', []),
                    'dietary_restrictions': metadata.get('dietary_restrictions', []),
                    'dietary_pattern': metadata.get('dietary_pattern'),
                    'nutrition_preferences': metadata.get('nutrition_preferences', []),
                    'spice_level': metadata.get('spice_level'),
                    'cooking_oil_preferences': metadata.get('cooking_oil_preferences', []),
                    'cuisines_preferences': metadata.get('cuisines_preferences', []),
                    'breakfast_preferences': metadata.get('breakfast_preferences', []),
                    'lunch_preferences': metadata.get('lunch_preferences', []),
                    'snacks_preferences': metadata.get('snacks_preferences', []),
                    'dinner_preferences': metadata.get('dinner_preferences', []),
                    'extra_input': metadata.get('extra_input'),
                }
            }
            users.append(user_profile)
        
        return {
            "success": True,
            "data": users,
            "count": len(users),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch users: {str(e)}"
        )
