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
        
        # First check if user exists (regardless of active status)
        # This prevents trying to create duplicate accounts for inactive users
        all_users_result = self.supabase.table('user_profiles') \
            .select('id, is_active') \
            .eq('firebase_uid', firebase_uid) \
            .execute()
        
        if all_users_result.data and len(all_users_result.data) > 0:
            # User exists - check if active
            user = all_users_result.data[0]
            user_id = user.get('id')
            is_active = user.get('is_active', True)  # Default to True if field doesn't exist
            
            if not user_id:
                raise ValueError(f"User record found but missing 'id' field. User data: {user}")
            
            if not is_active:
                # User exists but is deactivated
                raise ValueError("This account has been deactivated. Please contact support.")
            
            # Active user - update last_login and return
            print(f"Existing active user found: {user_id}")
            
            self.supabase.table('user_profiles') \
                .update({'last_login': datetime.utcnow().isoformat()}) \
                .eq('id', user_id) \
                .execute()
            
            # Ensure all fields are correct types
            return {
                'user_id': str(user_id),  # Ensure it's a string
                'phone_number': str(phone_number),  # Ensure it's a string
                'is_new_user': False
            }
        else:
            # New user - create with phone only
            print(f"Creating new user for: {phone_number}")
            
            new_user_data = {
                'firebase_uid': firebase_uid,
                'phone_number': phone_number,
                'is_active': True  # New users are active by default
            }
            
            new_user_result = self.supabase.table('user_profiles') \
                .insert(new_user_data) \
                .execute()
            
            if not new_user_result.data or len(new_user_result.data) == 0:
                raise ValueError("Failed to create new user - no data returned from Supabase")
            
            new_user = new_user_result.data[0]
            user_id = new_user.get('id')
            
            if not user_id:
                raise ValueError(f"New user created but missing 'id' field. User data: {new_user}")
            
            print(f"New user created: {user_id}")
            
            # Ensure all fields are correct types
            return {
                'user_id': str(user_id),  # Ensure it's a string
                'phone_number': str(phone_number),  # Ensure it's a string
                'is_new_user': True
            }
    
    async def update_user_profile(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user profile (name, metadata, etc.)
        Only updates active users. Returns updated user data.
        """
        # Verify user exists and is active before updating
        await self.get_user_by_id(user_id)
        
        # Protected fields that cannot be updated
        protected_fields = ['id', 'firebase_uid', 'phone_number', 'created_at']
        clean_data = {k: v for k, v in update_data.items() if k not in protected_fields}
        
        if not clean_data:
            raise ValueError("No valid fields to update")
        
        print(f"Updating user {user_id} with data: {clean_data}")
        
        result = self.supabase.table('user_profiles') \
            .update(clean_data) \
            .eq('id', user_id) \
            .eq('is_active', True) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id} or account has been deactivated")
        
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
        Get user profile by user_id.
        Only returns active users. Raises ValueError if user not found or inactive.
        """
        result = self.supabase.table('user_profiles') \
            .select('*') \
            .eq('id', user_id) \
            .eq('is_active', True) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id} or account has been deactivated")
        
        user = result.data[0]
        return user
    
    async def deactivate_user(self, user_id: str) -> Dict[str, Any]:
        """
        Deactivate a user by setting is_active to False.
        
        Args:
            user_id: UUID of the user to deactivate
            
        Returns:
            dict: Updated user profile with is_active = False
            
        Raises:
            ValueError: If user not found
        """
        result = self.supabase.table('user_profiles') \
            .update({'is_active': False}) \
            .eq('id', user_id) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id}")
        
        print(f"User {user_id} has been deactivated")
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