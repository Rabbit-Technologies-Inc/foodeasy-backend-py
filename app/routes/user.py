# app/routes/user.py

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
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

