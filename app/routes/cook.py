# app/routes/cook.py

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from app.services.cook_service import cook_service
from app.dependencies.auth import verify_user_access
from typing import Dict, Any, List, Optional

router = APIRouter(prefix="/cook", tags=["Cook Management"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class AddCookRequest(BaseModel):
    """Request to add a new cook"""
    name: str = Field(..., min_length=1, max_length=100, description="Cook's full name")
    phone_number: str = Field(..., min_length=10, max_length=15, description="Cook's phone number")
    languages_known: List[str] = Field(default=[], description="Languages the cook knows")
    has_smart_phone: bool = Field(default=False, description="Whether cook has a smartphone")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Ramesh Kumar",
                "phone_number": "9876543210",
                "languages_known": ["Hindi", "English"],
                "has_smart_phone": True
            }
        }


class UpdateCookRequest(BaseModel):
    """Request to update cook details"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Cook's full name")
    phone_number: Optional[str] = Field(None, min_length=10, max_length=15, description="Cook's phone number")
    languages_known: Optional[List[str]] = Field(None, description="Languages the cook knows")
    has_smart_phone: Optional[bool] = Field(None, description="Whether cook has a smartphone")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Ramesh Kumar",
                "languages_known": ["Hindi", "English", "Tamil"],
                "has_smart_phone": True
            }
        }


# ============================================
# COOK ENDPOINTS
# ============================================

@router.post(
    "/user/{user_id}/cooks",
    status_code=status.HTTP_201_CREATED,
    summary="Add a new cook",
    description="""
    Add cook details for a user.
    
    **Authentication Required:** Bearer token in Authorization header.
    """
)
async def add_cook(
    request: AddCookRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Add a new cook for the user.
    """
    try:
        cook_data = request.dict()
        new_cook = await cook_service.add_cook(user_id, cook_data)
        
        return {
            "success": True,
            "message": "Cook added successfully",
            "data": new_cook
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in add_cook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add cook"
        )


@router.get(
    "/user/{user_id}/cooks",
    status_code=status.HTTP_200_OK,
    summary="Get all cooks for a user",
    description="""
    Retrieve all cooks associated with a user.
    
    **Authentication Required:** Bearer token in Authorization header.
    """
)
async def get_user_cooks(
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Get all cooks for a user.
    """
    try:
        cooks = await cook_service.get_user_cooks(user_id)
        
        return {
            "success": True,
            "data": cooks,
            "count": len(cooks)
        }
    except Exception as e:
        print(f"Error in get_user_cooks: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch cooks"
        )


@router.get(
    "/user/{user_id}/cooks/{cook_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a specific cook",
    description="""
    Get details of a specific cook.
    
    **Authentication Required:** Bearer token in Authorization header.
    """
)
async def get_cook(
    cook_id: str,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Get a specific cook by ID.
    """
    try:
        cook = await cook_service.get_cook_by_id(cook_id, user_id)
        
        return {
            "success": True,
            "data": cook
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in get_cook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch cook"
        )


@router.put(
    "/user/{user_id}/cooks/{cook_id}",
    status_code=status.HTTP_200_OK,
    summary="Update cook details",
    description="""
    Update information for a specific cook.
    
    **Authentication Required:** Bearer token in Authorization header.
    """
)
async def update_cook(
    cook_id: str,
    request: UpdateCookRequest,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Update cook details.
    """
    try:
        update_data = request.dict(exclude_none=True)
        updated_cook = await cook_service.update_cook(cook_id, user_id, update_data)
        
        return {
            "success": True,
            "message": "Cook updated successfully",
            "data": updated_cook
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in update_cook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update cook"
        )


@router.delete(
    "/user/{user_id}/cooks/{cook_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a cook",
    description="""
    Remove a cook from the user's list.
    
    **Authentication Required:** Bearer token in Authorization header.
    """
)
async def delete_cook(
    cook_id: str,
    user_id: str = Depends(verify_user_access)
) -> Dict[str, Any]:
    """
    Delete a cook.
    """
    try:
        result = await cook_service.delete_cook(cook_id, user_id)
        
        return {
            "success": True,
            **result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in delete_cook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete cook"
        )