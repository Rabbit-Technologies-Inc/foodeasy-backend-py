#!/usr/bin/env python3
"""
Dev-only: Issue a bearer token for a phone number without OTP verification.
Use when Twilio limits block normal login (e.g. during development).
Usage: python -m scripts.issue_dev_token <phone_number>
Example: python -m scripts.issue_dev_token +919902637099
"""
import sys
from datetime import datetime, timezone

# Allow running from project root
sys.path.insert(0, ".")


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: python -m scripts.issue_dev_token <phone_number>")
        print("Example: python -m scripts.issue_dev_token +919902637099")
        sys.exit(1)
    phone = sys.argv[1].strip()

    from app.services.supabase_client import get_supabase_admin
    from app.services.jwt_service import create_access_token

    supabase = get_supabase_admin()
    result = supabase.table("user_profiles").select("id, is_active").eq("phone_number", phone).execute()

    if result.data and len(result.data) > 0:
        user = result.data[0]
        user_id = user.get("id")
        is_active = user.get("is_active", True)
        if not user_id:
            print("Error: User record missing id.")
            sys.exit(1)
        if not is_active:
            print("Error: Account is deactivated.")
            sys.exit(1)
        supabase.table("user_profiles").update({"last_login": datetime.now(timezone.utc).isoformat()}).eq("id", user_id).execute()
        print(f"Found existing user: {user_id}")
    else:
        new_user_data = {"phone_number": phone, "is_active": True}
        insert_result = supabase.table("user_profiles").insert(new_user_data).execute()
        if not insert_result.data or len(insert_result.data) == 0:
            print("Error: Failed to create user.")
            sys.exit(1)
        user_id = insert_result.data[0].get("id")
        print(f"Created new user: {user_id}")

    token = create_access_token(str(user_id), phone)
    print()
    print("Bearer token (use in Authorization header):")
    print(token)
    print()
    print("Header:")
    print(f"Authorization: Bearer {token}")


if __name__ == "__main__":
    main()
