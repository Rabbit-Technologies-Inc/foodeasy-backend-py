# app/services/periskope_service.py

import httpx
import os
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()

# Periskope API configuration
PERISKOPE_API_BASE_URL = os.getenv("PERISKOPE_API_BASE_URL")
PERISKOPE_API_TOKEN = os.getenv("PERISKOPE_API_TOKEN")
PERISKOPE_PHONE_NUMBER = os.getenv("PERISKOPE_PHONE_NUMBER")

# Default image URL for Foodeasy groups
FOODEASY_GROUP_IMAGE_URL = os.getenv(
    "FOODEASY_GROUP_IMAGE_URL"
)


class PeriskopeService:
    """Service for interacting with Periskope API to create WhatsApp groups"""
    
    def __init__(self):
        if not PERISKOPE_API_TOKEN:
            raise ValueError(
                "PERISKOPE_API_TOKEN environment variable is not set. "
                "Please set it in your .env file."
            )
        if not PERISKOPE_PHONE_NUMBER:
            raise ValueError(
                "PERISKOPE_PHONE_NUMBER environment variable is not set. "
                "Please set it in your .env file (e.g., '919952907025')."
            )
    
    async def create_whatsapp_group(
        self,
        group_name: str,
        participants: Optional[List[str]] = None,
        description: Optional[str] = None,
        image_url: Optional[str] = None,
        messages_admins_only: bool = False,
        info_admins_only: bool = False,
        add_members_admins_only: bool = False,
        force_add_participants: bool = False
    ) -> Dict[str, Any]:
        """
        Create a WhatsApp group using Periskope API.
        
        Args:
            group_name: Name of the WhatsApp group
            participants: List of participant phone numbers (optional)
            description: Group description (optional)
            image_url: URL of the group image (optional, defaults to Foodeasy image)
            messages_admins_only: Only admins can send messages (default: False)
            info_admins_only: Only admins can change group info (default: False)
            add_members_admins_only: Only admins can add members (default: False)
            force_add_participants: Force add participants even if they haven't joined (default: False)
        
        Returns:
            Dict containing the API response with group creation details
        
        Raises:
            httpx.HTTPStatusError: If the API request fails
            Exception: For other errors
        """
        if participants is None:
            participants = []
        
        if image_url is None:
            image_url = FOODEASY_GROUP_IMAGE_URL
        
        url = f"{PERISKOPE_API_BASE_URL}/chats/create"
        
        headers = {
            "x-phone": PERISKOPE_PHONE_NUMBER,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {PERISKOPE_API_TOKEN}"
        }
        
        payload = {
            "group_name": group_name,
            "participants": participants,
            "options": {
                "description": description or "",
                "image": image_url,
                "messagesAdminsOnly": messages_admins_only,
                "infoAdminsOnly": info_admins_only,
                "addMembersAdminsOnly": add_members_admins_only,
                "force_add_participants": force_add_participants
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = None
            try:
                error_json = e.response.json()
                error_detail = error_json.get("detail") or error_json.get("message") or str(error_json)
            except:
                error_detail = e.response.text or str(e)
            
            raise Exception(
                f"Periskope API error ({e.response.status_code}): {error_detail}"
            )
        except httpx.RequestError as e:
            raise Exception(f"Network error calling Periskope API: {str(e)}")
        except Exception as e:
            raise Exception(f"Error creating WhatsApp group: {str(e)}")


# Create a singleton instance
_periskope_service: Optional[PeriskopeService] = None


def get_periskope_service() -> PeriskopeService:
    """Get or create the Periskope service instance"""
    global _periskope_service
    if _periskope_service is None:
        _periskope_service = PeriskopeService()
    return _periskope_service
