# test/routes/test_user_creation.py

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path as PathLib
from app.services.supabase_client import get_supabase_admin
from app.services.auth_service import auth_service
import uuid

router = APIRouter(prefix="/test/user-creation", tags=["Test User Creation"])

# Setup templates - use absolute path relative to this file
template_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))


class CreateTestUserRequest(BaseModel):
    """Request to create a test user with onboarding data"""
    full_name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    age: Optional[int] = Field(None, ge=1, le=120, description="User age")
    total_household_adults: Optional[int] = Field(1, ge=1, description="Number of adults in household")
    total_household_children: Optional[int] = Field(0, ge=0, description="Number of children in household")
    
    # Onboarding selections (all are TEXT values/names, not IDs)
    goals: List[str] = Field(default=[], description="Selected goal names")
    medical_restrictions: List[str] = Field(default=[], description="Medical restriction names")
    dietary_pattern: Optional[str] = Field(None, description="Dietary pattern name")
    nutrition_preferences: List[str] = Field(default=[], description="Nutrition preference names")
    dietary_restrictions: List[str] = Field(default=[], description="Dietary restriction names")
    cuisines_preferences: List[str] = Field(default=[], description="Cuisine names")
    breakfast_preferences: List[str] = Field(default=[], description="Breakfast item names")
    lunch_preferences: List[str] = Field(default=[], description="Lunch item names")
    snacks_preferences: List[str] = Field(default=[], description="Snack item names")
    dinner_preferences: List[str] = Field(default=[], description="Dinner item names")
    
    # Additional input
    extra_input: Optional[str] = Field(None, max_length=1000, description="Additional notes/preferences")
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Test User",
                "age": 28,
                "total_household_adults": 2,
                "total_household_children": 1,
                "goals": ["Weight Loss", "Muscle Gain"],
                "medical_restrictions": ["Diabetes"],
                "dietary_pattern": "Vegetarian",
                "nutrition_preferences": ["High Protein"],
                "dietary_restrictions": ["No Onion No Garlic"],
                "cuisines_preferences": ["North Indian", "South Indian"],
                "breakfast_preferences": ["Idli", "Poha"],
                "lunch_preferences": ["Dal Rice"],
                "snacks_preferences": ["Samosa"],
                "dinner_preferences": ["Roti Sabzi"],
                "extra_input": "I prefer early dinner around 7 PM"
            }
        }


@router.get("/", response_class=HTMLResponse)
async def get_user_creation_ui(request: Request):
    """Serve the test user creation UI"""
    try:
        return templates.TemplateResponse(
            "test_user_creation.html",
            {"request": request}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load UI: {str(e)}"
        )


@router.get(
    "/onboarding-data",
    status_code=status.HTTP_200_OK,
    summary="Get all onboarding data for the UI",
    description="Fetch all available options for dropdowns (goals, dietary patterns, meal items, etc.)"
)
async def get_onboarding_data() -> Dict[str, Any]:
    """Get all onboarding data for populating the UI dropdowns"""
    try:
        # Use the existing onboarding endpoint logic
        from app.routes.onboarding import get_all_onboarding_data
        result = await get_all_onboarding_data()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch onboarding data: {str(e)}"
        )


@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create a test user with onboarding data",
    description="""
    Create a test user without OTP verification.
    This bypasses Firebase authentication and creates a user directly in Supabase.
    """
)
async def create_test_user(
    request: CreateTestUserRequest
) -> Dict[str, Any]:
    """Create a test user with complete onboarding data"""
    supabase = get_supabase_admin()
    
    try:
        # Generate a unique test Firebase UID for test users
        test_firebase_uid = f"test_{str(uuid.uuid4())}"
        
        # Create a dummy phone number for test users (some databases require phone_number)
        # Use a format that clearly indicates it's a test user
        test_phone_number = f"+91TEST{uuid.uuid4().hex[:8]}"
        
        # Create user profile in Supabase
        # Let Supabase auto-generate the ID
        user_data = {
            'firebase_uid': test_firebase_uid,
            'phone_number': test_phone_number,  # Use test phone number instead of None
            'full_name': request.full_name
        }
        
        # Prepare metadata with all onboarding data
        metadata = {
            'age': request.age,
            'total_household_adults': request.total_household_adults,
            'total_household_children': request.total_household_children,
            'goals': request.goals,
            'medical_restrictions': request.medical_restrictions,
            'dietary_pattern': request.dietary_pattern,
            'nutrition_preferences': request.nutrition_preferences,
            'dietary_restrictions': request.dietary_restrictions,
            'cuisines_preferences': request.cuisines_preferences,
            'breakfast_preferences': request.breakfast_preferences,
            'lunch_preferences': request.lunch_preferences,
            'snacks_preferences': request.snacks_preferences,
            'dinner_preferences': request.dinner_preferences,
            'extra_input': request.extra_input,
            'onboarding_completed': True,
            'onboarding_completed_at': datetime.utcnow().isoformat(),
            'is_test_user': True  # Flag to identify test users
        }
        
        user_data['metadata'] = metadata
        
        # Insert user into database
        print(f"Attempting to create test user with data: {user_data}")
        result = supabase.table('user_profiles') \
            .insert(user_data) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            print("Error: No data returned from Supabase insert")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create test user - no data returned from database"
            )
        
        created_user = result.data[0]
        
        return {
            "success": True,
            "message": "Test user created successfully",
            "data": {
                "user_id": str(created_user.get('id')),
                "full_name": created_user.get('full_name'),
                "firebase_uid": created_user.get('firebase_uid'),
                "metadata": metadata
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error creating test user: {str(e)}")
        print(f"Traceback: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test user: {str(e)}"
        )
