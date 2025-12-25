# app/services/auth_service.py

from app.services.supabase_client import get_supabase_admin
from app.services.firebase_service import verify_firebase_token
from firebase_admin import auth as firebase_auth
from typing import Dict, Any, List
from datetime import datetime


class AuthService:
    """
    Service class for handling phone authentication logic.
    Manages integration between Firebase Phone Auth and Supabase user storage.
    """
    
    def __init__(self):
        self.supabase = get_supabase_admin()
    
    async def verify_and_sync_user(self, id_token: str) -> Dict[str, Any]:
        """
        Verify Firebase ID token and sync user with Supabase.
        """
        # Verify Firebase token
        decoded_token = verify_firebase_token(id_token)
        
        firebase_uid = decoded_token.get('uid')
        phone_number = decoded_token.get('phone_number')
        
        if not phone_number:
            raise ValueError("Phone number not found in Firebase token")
        
        print(f"Verified Firebase user: {firebase_uid}, Phone: {phone_number}")
        
        # Check if user exists
        result = self.supabase.table('user_profiles') \
            .select('*') \
            .eq('firebase_uid', firebase_uid) \
            .execute()
        
        if result.data and len(result.data) > 0:
            # Existing user - update last_login
            user = result.data[0]
            print(f"Existing user found: {user['id']}")
            
            self.supabase.table('user_profiles') \
                .update({'last_login': datetime.utcnow().isoformat()}) \
                .eq('id', user['id']) \
                .execute()
            
            return {
                'user_id': user['id'],
                'phone_number': phone_number,
                'is_new_user': False
            }
        else:
            # New user - create with phone only
            print(f"Creating new user for: {phone_number}")
            
            new_user_data = {
                'firebase_uid': firebase_uid,
                'phone_number': phone_number
            }
            
            new_user_result = self.supabase.table('user_profiles') \
                .insert(new_user_data) \
                .execute()
            
            new_user = new_user_result.data[0]
            print(f"New user created: {new_user['id']}")
            
            return {
                'user_id': new_user['id'],
                'phone_number': phone_number,
                'is_new_user': True
            }
    
    async def update_user_profile(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user profile (name, metadata, etc.)
        """
        # Protected fields that cannot be updated
        protected_fields = ['id', 'firebase_uid', 'phone_number', 'created_at']
        clean_data = {k: v for k, v in update_data.items() if k not in protected_fields}
        
        if not clean_data:
            raise ValueError("No valid fields to update")
        
        print(f"Updating user {user_id} with data: {clean_data}")
        
        result = self.supabase.table('user_profiles') \
            .update(clean_data) \
            .eq('id', user_id) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id}")
        
        return result.data[0]
    
    async def update_onboarding_data(self, user_id: str, onboarding_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user's complete onboarding data.
        
        Stores:
        - full_name: Direct column in user_profiles table
        - All other data in metadata JSONB column:
          - Basic info (age, gender, household)
          - Onboarding status (onboarding_completed, onboarding_completed_at)
          - All preferences as text/arrays
        
        Args:
            user_id: UUID of the user
            onboarding_data: Dictionary containing all onboarding data (with text values, not IDs)
            
        Returns:
            dict: Updated user profile
        """
        try:
            # Get current user data
            user = await self.get_user_by_id(user_id)
            current_metadata = user.get('metadata', {})
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            
            # Separate full_name (direct column) from metadata fields
            full_name = onboarding_data.get('full_name')
            update_columns = {}
            
            if full_name is not None:
                update_columns['full_name'] = full_name
            
            # Store everything else in metadata JSONB column
            metadata_fields = {
                # Basic demographics
                'age': onboarding_data.get('age'),
                'gender': onboarding_data.get('gender'),
                'total_household_adults': onboarding_data.get('total_household_adults', 1),
                'total_household_children': onboarding_data.get('total_household_children', 0),
                
                # Onboarding status
                'onboarding_completed': True,
                'onboarding_completed_at': datetime.utcnow().isoformat(),
                
                # Onboarding preferences (as text, not IDs)
                'goals': onboarding_data.get('goals', []),
                'medical_restrictions': onboarding_data.get('medical_restrictions', []),
                'dietary_pattern': onboarding_data.get('dietary_pattern'),
                'nutrition_preferences': onboarding_data.get('nutrition_preferences', []),
                'dietary_restrictions': onboarding_data.get('dietary_restrictions', []),
                'spice_level': onboarding_data.get('spice_level'),
                'cooking_oil_preferences': onboarding_data.get('cooking_oil_preferences', []),
                'cuisines_preferences': onboarding_data.get('cuisines_preferences', []),
                'breakfast_preferences': onboarding_data.get('breakfast_preferences', []),
                'lunch_preferences': onboarding_data.get('lunch_preferences', []),
                'snacks_preferences': onboarding_data.get('snacks_preferences', []),
                'dinner_preferences': onboarding_data.get('dinner_preferences', []),
                'extra_input': onboarding_data.get('extra_input', '')
            }
            
            # Merge with existing metadata (preserve other custom metadata)
            current_metadata.update(metadata_fields)
            update_columns['metadata'] = current_metadata
            
            # Update database with both full_name (if provided) and metadata
            result = self.supabase.table('user_profiles') \
                .update(update_columns) \
                .eq('id', user_id) \
                .execute()
            
            if not result.data or len(result.data) == 0:
                raise ValueError(f"User not found with user_id: {user_id}")
            
            print(f"Onboarding data updated for user: {user_id}")
            return result.data[0]
            
        except Exception as e:
            print(f"Error updating onboarding data: {str(e)}")
            raise
    
    async def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile by user_id
        """
        result = self.supabase.table('user_profiles') \
            .select('*') \
            .eq('id', user_id) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id}")
        
        return result.data[0]
    
    async def get_onboarding_status(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user has completed onboarding.
        
        Reads onboarding status from metadata JSONB column.
        """
        try:
            user = await self.get_user_by_id(user_id)
            metadata = user.get('metadata', {})
            if not isinstance(metadata, dict):
                metadata = {}
            
            return {
                'user_id': user_id,
                'onboarding_completed': metadata.get('onboarding_completed', False),
                'onboarding_completed_at': metadata.get('onboarding_completed_at'),
                'has_name': user.get('full_name') is not None
            }
        except Exception as e:
            print(f"Error getting onboarding status: {str(e)}")
            raise


# Create singleton instance
auth_service = AuthService()