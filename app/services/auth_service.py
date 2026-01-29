# app/services/auth_service.py

from app.services.supabase_client import get_supabase_admin
from app.services.twilio_otp_service import send_otp as twilio_send_otp, verify_otp as twilio_verify_otp
from app.services.jwt_service import create_access_token
from typing import Dict, Any, List
from datetime import datetime


class AuthService:
    """
    Service class for phone authentication via Twilio Verify (OTP) and backend-issued JWT.
    Users are stored in Supabase; identity is by phone_number.
    """
    
    def __init__(self):
        self.supabase = get_supabase_admin()
    
    def send_otp(self, phone_number: str) -> None:
        """Send OTP to the given phone number via Twilio Verify (SMS)."""
        twilio_send_otp(phone_number)
    
    async def verify_otp_and_issue_tokens(self, phone_number: str, otp_code: str) -> Dict[str, Any]:
        """
        Verify OTP with Twilio, find or create user in Supabase by phone_number,
        then issue backend JWT (infinite expiry). Returns user_id, phone_number, is_new_user, access_token.
        """
        if not twilio_verify_otp(phone_number, otp_code):
            raise ValueError("Invalid or expired verification code.")
        
        # Find user by phone_number (any active status first to handle deactivated)
        all_users_result = self.supabase.table('user_profiles') \
            .select('id, is_active') \
            .eq('phone_number', phone_number) \
            .execute()
        
        if all_users_result.data and len(all_users_result.data) > 0:
            user = all_users_result.data[0]
            user_id = user.get('id')
            is_active = user.get('is_active', True)
            if not user_id:
                raise ValueError(f"User record missing 'id'. User data: {user}")
            if not is_active:
                raise ValueError("This account has been deactivated. Please contact support.")
            print(f"Existing active user found: {user_id}")
            self.supabase.table('user_profiles') \
                .update({'last_login': datetime.utcnow().isoformat()}) \
                .eq('id', user_id) \
                .execute()
            is_new_user = False
        else:
            print(f"Creating new user for: {phone_number}")
            new_user_data = {
                'phone_number': phone_number,
                'is_active': True,
            }
            new_user_result = self.supabase.table('user_profiles') \
                .insert(new_user_data) \
                .execute()
            if not new_user_result.data or len(new_user_result.data) == 0:
                raise ValueError("Failed to create new user - no data returned from Supabase")
            new_user = new_user_result.data[0]
            user_id = new_user.get('id')
            if not user_id:
                raise ValueError(f"New user created but missing 'id'. User data: {new_user}")
            print(f"New user created: {user_id}")
            is_new_user = True
        
        user_id_str = str(user_id)
        access_token = create_access_token(user_id_str, phone_number)
        return {
            'user_id': user_id_str,
            'phone_number': phone_number,
            'is_new_user': is_new_user,
            'access_token': access_token,
        }
    
    async def update_user_profile(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user profile (name, metadata, etc.)
        Only updates active users. Returns updated user data.
        """
        # Verify user exists and is active before updating
        await self.get_user_by_id(user_id)
        
        # Protected fields that cannot be updated
        protected_fields = ['id', 'phone_number', 'created_at']
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
    
    async def hard_delete_user(self, user_id: str) -> None:
        """
        Permanently delete a user and all related data.
        Deletion order: user_meal_plan_details -> user_meal_plan -> cooks -> user_profiles.
        
        Args:
            user_id: UUID of the user to delete
            
        Raises:
            ValueError: If user not found in user_profiles
        """
        # Check user exists (any is_active status)
        check = self.supabase.table('user_profiles') \
            .select('id') \
            .eq('id', user_id) \
            .execute()
        if not check.data or len(check.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id}")
        
        # Get all user_meal_plan ids for this user
        plans_result = self.supabase.table('user_meal_plan') \
            .select('id') \
            .eq('user_id', user_id) \
            .execute()
        plan_ids = [p['id'] for p in (plans_result.data or [])]
        
        # Delete user_meal_plan_details for those plans
        if plan_ids:
            for plan_id in plan_ids:
                self.supabase.table('user_meal_plan_details') \
                    .delete() \
                    .eq('user_meal_plan_id', plan_id) \
                    .execute()
        
        # Delete user_meal_plan
        self.supabase.table('user_meal_plan') \
            .delete() \
            .eq('user_id', user_id) \
            .execute()
        
        # Delete cooks
        self.supabase.table('cooks') \
            .delete() \
            .eq('user_id', user_id) \
            .execute()
        
        # Delete user_profiles
        self.supabase.table('user_profiles') \
            .delete() \
            .eq('id', user_id) \
            .execute()
        
        print(f"User {user_id} has been hard deleted")
    
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