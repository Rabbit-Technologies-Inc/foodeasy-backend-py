"""
Simple test script for the combined onboarding API endpoint.
Run this after starting the FastAPI server with: uvicorn app.main:app --reload
"""

import httpx
import json

# API endpoint
URL = "http://localhost:8000/onboarding"

def test_combined_api():
    """Test the combined onboarding endpoint"""
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(URL)
            
            print(f"Status Code: {response.status_code}")
            print(f"\nResponse:\n{json.dumps(response.json(), indent=2)}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print("\n✅ API call successful!")
                    onboarding_data = data.get("data", {})
                    print("\nData Summary:")
                    for key, value in onboarding_data.items():
                        count = len(value) if isinstance(value, list) else 0
                        print(f"  - {key}: {count} items")
    except httpx.ConnectError:
        print("❌ Error: Could not connect to server.")
        print("   Make sure server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_combined_api()
