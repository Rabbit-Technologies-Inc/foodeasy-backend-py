#!/usr/bin/env python3
"""
Cron job to manage user meal plans.

This script:
1. Fetches all active meal plans from the database
2. Inactivates meal plans where end_date < today (sets is_active = False)
3. Generates new meal plans for users whose meal plan end_date is exactly 2 days before today
   (new meal plan start_date = old end_date + 1 day)
4. Sends WhatsApp notification to users when their new meal plan is generated (if chat_id is available)
5. Logs the results

Run this script as a cron job, e.g.:
    # Run daily at 2 AM
    0 2 * * * cd /path/to/foodeasy-backend && python3 cron_jobs/manage_meal_plans.py

Environment Variables Required:
    - PERISKOPE_PHONE_NUMBER: Phone number for Periskope API
    - PERISKOPE_API_TOKEN: Bearer token for Periskope API
    - PERISKOPE_API_BASE_URL: Base URL for Periskope API (defaults to https://api.periskope.app)
"""

import sys
import os
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import asyncio
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.supabase_client import get_supabase_admin
from app.services.meal_generation_service import meal_generation_service
from app.services.auth_service import auth_service


def get_all_active_meal_plans() -> List[Dict[str, Any]]:
    """
    Fetch all active meal plans from the database.
    
    Returns:
        List of meal plan dictionaries with user_id, id, start_date, end_date
    """
    supabase = get_supabase_admin()
    
    try:
        response = supabase.table("user_meal_plan") \
            .select("id, user_id, start_date, end_date, is_active") \
            .eq("is_active", True) \
            .execute()
        
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching active meal plans: {str(e)}")
        raise


def inactivate_meal_plan(meal_plan_id: int) -> bool:
    """
    Set is_active = False for a meal plan.
    
    Args:
        meal_plan_id: ID of the meal plan to inactivate
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase_admin()
    
    try:
        response = supabase.table("user_meal_plan") \
            .update({"is_active": False}) \
            .eq("id", meal_plan_id) \
            .execute()
        
        return response.data is not None and len(response.data) > 0
    except Exception as e:
        print(f"Error inactivating meal plan {meal_plan_id}: {str(e)}")
        return False


async def _get_meal_type_mapping(supabase) -> Dict[str, int]:
    """
    Get mapping of meal type names to meal_type_id from database.
    Returns dict like: {"breakfast": 1, "lunch": 2, "snacks": 3, "dinner": 4}
    """
    try:
        response = supabase.table("meal_types") \
            .select("id, name") \
            .eq("is_active", True) \
            .execute()
        
        mapping = {}
        for meal_type in response.data:
            name = meal_type.get("name", "").lower().strip()
            meal_id = meal_type.get("id")
            if name and meal_id:
                mapping[name] = meal_id
        
        # Ensure we have all required meal types
        breakfast_id = None
        lunch_id = None
        snacks_id = None
        dinner_id = None
        
        for name, meal_id in mapping.items():
            if "breakfast" in name:
                breakfast_id = meal_id
            elif "lunch" in name:
                lunch_id = meal_id
            elif "snack" in name:
                snacks_id = meal_id
            elif "dinner" in name:
                dinner_id = meal_id
        
        final_mapping = {}
        if breakfast_id:
            final_mapping["breakfast"] = breakfast_id
        if lunch_id:
            final_mapping["lunch"] = lunch_id
        if snacks_id:
            final_mapping["snacks"] = snacks_id
        if dinner_id:
            final_mapping["dinner"] = dinner_id
        
        return final_mapping
    except Exception as e:
        print(f"Error getting meal type mapping: {str(e)}")
        return {}


async def generate_and_store_meal_plan(user_id: str, start_date: date) -> Optional[Dict[str, Any]]:
    """
    Generate and store a meal plan for a user.
    
    Args:
        user_id: UUID of the user
        start_date: Start date for the meal plan
        
    Returns:
        Dictionary with meal plan details if successful, None otherwise
    """
    supabase = get_supabase_admin()
    
    try:
        # Calculate end date (7 days from start)
        end_date = start_date + timedelta(days=6)
        
        # Check if a meal plan already exists for this user and date range
        existing_plan_response = supabase.table("user_meal_plan") \
            .select("id, start_date, end_date") \
            .eq("user_id", user_id) \
            .eq("start_date", start_date.isoformat()) \
            .eq("end_date", end_date.isoformat()) \
            .execute()
        
        if existing_plan_response.data and len(existing_plan_response.data) > 0:
            print(f"Meal plan already exists for user {user_id} from {start_date.isoformat()} to {end_date.isoformat()}")
            return None
        
        # Generate meal plan using the service
        meal_plan_data = await meal_generation_service.generate_meal_plan(
            user_id=user_id,
            start_date=datetime.combine(start_date, datetime.min.time())
        )
        
        # Validate meal plan structure
        if "meal_plan" not in meal_plan_data:
            print(f"Invalid meal plan format for user {user_id}")
            return None
        
        # Get meal type mappings
        meal_type_mapping = await _get_meal_type_mapping(supabase)
        
        # Create user_meal_plan record
        meal_plan_record = {
            "user_id": user_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "is_active": True
        }
        
        plan_response = supabase.table("user_meal_plan") \
            .insert(meal_plan_record) \
            .execute()
        
        if not plan_response.data or len(plan_response.data) == 0:
            print(f"Failed to create meal plan record for user {user_id}")
            return None
        
        user_meal_plan_id = plan_response.data[0]["id"]
        
        # Prepare meal plan details to insert
        meal_plan_details = []
        total_meals = 0
        
        for day_plan in meal_plan_data.get("meal_plan", []):
            day_date = day_plan.get("date")
            if not day_date:
                continue
            
            # Parse date string to date object
            try:
                day_date_obj = datetime.strptime(day_date, "%Y-%m-%d").date()
            except ValueError:
                try:
                    day_date_obj = datetime.fromisoformat(day_date.replace("Z", "+00:00")).date()
                except:
                    print(f"Invalid date format: {day_date}")
                    continue
            
            # Process each meal type
            for meal_type_name, meal_items in day_plan.items():
                if meal_type_name == "date" or not meal_items:
                    continue
                
                meal_type_id = meal_type_mapping.get(meal_type_name.lower())
                if not meal_type_id:
                    continue
                
                # Handle both list and single item formats
                if not isinstance(meal_items, list):
                    meal_items = [meal_items]
                
                for meal_item in meal_items:
                    meal_item_id = meal_item.get("id") if isinstance(meal_item, dict) else meal_item
                    if not meal_item_id:
                        continue
                    
                    meal_plan_details.append({
                        "user_meal_plan_id": user_meal_plan_id,
                        "date": day_date_obj.isoformat(),
                        "meal_type_id": meal_type_id,
                        "meal_item_id": meal_item_id,
                        "is_active": True
                    })
                    total_meals += 1
        
        # Bulk insert meal plan details
        if meal_plan_details:
            details_response = supabase.table("user_meal_plan_details") \
                .insert(meal_plan_details) \
                .execute()
            
            if not details_response.data:
                # Rollback: delete the meal plan if details insertion failed
                supabase.table("user_meal_plan") \
                    .delete() \
                    .eq("id", user_meal_plan_id) \
                    .execute()
                
                print(f"Failed to create meal plan details for user {user_id}")
                return None
        
        return {
            "user_meal_plan_id": user_meal_plan_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_meals": total_meals,
            "total_days": 7
        }
        
    except Exception as e:
        print(f"Error generating meal plan for user {user_id}: {str(e)}")
        return None


async def get_user_chat_id(user_id: str) -> Optional[str]:
    """
    Get the WhatsApp chat_id from user's metadata.
    
    Args:
        user_id: UUID of the user
        
    Returns:
        chat_id string if found, None otherwise
    """
    try:
        # Get user data using supabase directly (synchronous) - only active users
        supabase = get_supabase_admin()
        result = supabase.table('user_profiles') \
            .select('metadata') \
            .eq('id', user_id) \
            .eq('is_active', True) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return None
        
        metadata = result.data[0].get('metadata', {})
        if not isinstance(metadata, dict):
            return None
        
        # Check for chat_id directly in metadata
        chat_id = metadata.get('chat_id')
        if chat_id:
            return chat_id
        
        # Check in whatsapp_group_metadata
        whatsapp_metadata = metadata.get('whatsapp_group_metadata', {})
        if isinstance(whatsapp_metadata, dict):
            chat_id = whatsapp_metadata.get('chat_id') or whatsapp_metadata.get('id')
            if chat_id:
                return chat_id
        
        return None
    except Exception as e:
        print(f"Error getting chat_id for user {user_id}: {str(e)}")
        return None


async def send_whatsapp_message(chat_id: str, message: str) -> bool:
    """
    Send a WhatsApp message via Periskope API.
    
    Args:
        chat_id: WhatsApp chat ID (e.g., "919876543210@c.us")
        message: Message text to send
        
    Returns:
        True if successful, False otherwise
    """
    try:
        periskope_phone = os.getenv("PERISKOPE_PHONE_NUMBER")
        periskope_token = os.getenv("PERISKOPE_API_TOKEN")
        periskope_base_url = os.getenv("PERISKOPE_API_BASE_URL")
        
        if not periskope_phone or not periskope_token:
            print("PERISKOPE_PHONE_NUMBER or PERISKOPE_API_TOKEN not set in environment")
            return False
        
        url = f"{periskope_base_url}/message/send"
        headers = {
            "x-phone": periskope_phone,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {periskope_token}"
        }
        payload = {
            "chat_id": chat_id,
            "message": message
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                print(f"Successfully sent WhatsApp message to {chat_id}")
                return True
            else:
                print(f"Failed to send WhatsApp message. Status: {response.status_code}, Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"Error sending WhatsApp message: {str(e)}")
        return False


async def manage_meal_plans() -> Dict[str, Any]:
    """
    Main function to manage meal plans:
    1. Inactivate meal plans where end_date < today
    2. Generate new meal plans for users whose meal plan end_date is 2 days before today
    
    Returns:
        Dictionary with summary statistics
    """
    print(f"[{datetime.now().isoformat()}] Starting cron job: Manage user meal plans")
    
    try:
        today = date.today()
        two_days_ago = today - timedelta(days=2)
        
        # Get all active meal plans
        meal_plans = get_all_active_meal_plans()
        print(f"Found {len(meal_plans)} active meal plans")
        
        if not meal_plans:
            print("No active meal plans found")
            return {
                "success": True,
                "total_meal_plans": 0,
                "inactivated": 0,
                "new_plans_generated": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        inactivated_count = 0
        new_plans_generated = 0
        inactivated_plans = []
        plans_to_generate = []
        
        # Process each meal plan
        for meal_plan in meal_plans:
            meal_plan_id = meal_plan.get("id")
            user_id = meal_plan.get("user_id")
            end_date_str = meal_plan.get("end_date")
            
            if not end_date_str:
                continue
            
            # Parse end_date
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).date()
            except:
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except:
                    print(f"Invalid end_date format for meal plan {meal_plan_id}: {end_date_str}")
                    continue
            
            # Check if meal plan should be inactivated (end_date < today)
            if end_date < today:
                if inactivate_meal_plan(meal_plan_id):
                    inactivated_count += 1
                    inactivated_plans.append({
                        "meal_plan_id": meal_plan_id,
                        "user_id": user_id,
                        "end_date": end_date_str
                    })
                    print(f"Inactivated meal plan {meal_plan_id} for user {user_id} (end_date: {end_date_str})")
            
            # Check if meal plan should trigger new generation (end_date = today - 2 days)
            elif end_date == two_days_ago:
                new_start_date = end_date + timedelta(days=1)
                plans_to_generate.append({
                    "user_id": user_id,
                    "old_meal_plan_id": meal_plan_id,
                    "old_end_date": end_date_str,
                    "new_start_date": new_start_date
                })
                print(f"Scheduled new meal plan generation for user {user_id} (old plan ends: {end_date_str}, new starts: {new_start_date.isoformat()})")
        
        # Generate new meal plans
        for plan_info in plans_to_generate:
            user_id = plan_info["user_id"]
            new_start_date = plan_info["new_start_date"]
            
            print(f"Generating new meal plan for user {user_id} starting {new_start_date.isoformat()}...")
            result = await generate_and_store_meal_plan(user_id, new_start_date)
            
            if result:
                new_plans_generated += 1
                print(f"Successfully generated meal plan {result.get('user_meal_plan_id')} for user {user_id}")
                
                # Send WhatsApp message to user
                chat_id = await get_user_chat_id(user_id)
                if chat_id:
                    message = f"🎉 Your new meal plan is ready! It starts on {new_start_date.strftime('%B %d, %Y')} and covers the next 7 days. Check your app for details!"
                    await send_whatsapp_message(chat_id, message)
                else:
                    print(f"No chat_id found for user {user_id}, skipping WhatsApp notification")
            else:
                print(f"Failed to generate meal plan for user {user_id}")
        
        summary = {
            "success": True,
            "total_meal_plans": len(meal_plans),
            "inactivated": inactivated_count,
            "new_plans_generated": new_plans_generated,
            "inactivated_plans": inactivated_plans,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"\nSummary:")
        print(f"  Total active meal plans processed: {summary['total_meal_plans']}")
        print(f"  Meal plans inactivated: {summary['inactivated']}")
        print(f"  New meal plans generated: {summary['new_plans_generated']}")
        print(f"[{datetime.now().isoformat()}] Cron job completed successfully")
        
        return summary
        
    except Exception as e:
        error_msg = f"Error in cron job: {str(e)}"
        print(f"[{datetime.now().isoformat()}] {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    """
    Entry point for the cron job.
    Can be run directly: python3 cron_jobs/manage_meal_plans.py
    """
    result = asyncio.run(manage_meal_plans())
    
    # Exit with error code if job failed
    if not result.get("success", False):
        sys.exit(1)
    
    sys.exit(0)
