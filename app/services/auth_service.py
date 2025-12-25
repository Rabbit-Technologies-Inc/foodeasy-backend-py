# app/services/auth_service.py

from app.services.supabase_client import get_supabase_admin
from app.services.firebase_service import verify_firebase_token
from firebase_admin import auth as firebase_auth
from typing import Dict, Any
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
        
        Flow:
        1. Verify Firebase token
        2. Extract firebase_uid and phone_number
        3. Check if user exists by firebase_uid
        4. If exists: update last_login, return user_id
        5. If new: create user with phone only, return user_id
        
        Args:
            id_token: Firebase ID token from React Native
            
        Returns:
            dict: Contains user_id, phone_number, is_new_user
            
        Raises:
            ValueError: If phone number is missing from token
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
        
        Args:
            user_id: UUID of the user
            update_data: Dictionary of fields to update
            
        Returns:
            dict: Updated user profile
            
        Raises:
            ValueError: If no valid fields to update or user not found
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
    
    async def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile by user_id
        
        Args:
            user_id: UUID of the user
            
        Returns:
            dict: User profile data
            
        Raises:
            ValueError: If user not found
        """
        result = self.supabase.table('user_profiles') \
            .select('*') \
            .eq('id', user_id) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"User not found with user_id: {user_id}")
        
        return result.data[0]


# Create singleton instance
auth_service = AuthService()