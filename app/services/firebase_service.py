# app/services/firebase_admin.py

import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv
import os
from typing import Optional

load_dotenv()

# Get Firebase credentials path from environment
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# Validate credentials file exists
if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
    raise ValueError(
        f"Firebase credentials file not found at: {FIREBASE_CREDENTIALS_PATH}. "
        "Please download your service account key from Firebase Console and place it in the project root."
    )

# Initialize Firebase Admin SDK (only once)
_firebase_app: Optional[firebase_admin.App] = None


def get_firebase_app() -> firebase_admin.App:
    """
    Get or initialize Firebase Admin app.
    
    Returns:
        firebase_admin.App: Initialized Firebase app instance
    """
    global _firebase_app
    
    if _firebase_app is None:
        try:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
            print(f"✓ Firebase Admin SDK initialized successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Firebase Admin SDK: {str(e)}") from e
    
    return _firebase_app


def verify_firebase_token(id_token: str) -> dict:
    """
    Verify Firebase ID token and return decoded token data.
    
    Args:
        id_token: Firebase ID token from React Native client
        
    Returns:
        dict: Decoded token containing uid, phone_number, etc.
        
    Raises:
        auth.InvalidIdTokenError: If token is invalid
        auth.ExpiredIdTokenError: If token has expired
    """
    get_firebase_app()  # Ensure Firebase is initialized
    
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except auth.InvalidIdTokenError as e:
        raise auth.InvalidIdTokenError(f"Invalid Firebase token: {str(e)}")
    except auth.ExpiredIdTokenError as e:
        raise auth.ExpiredIdTokenError(f"Firebase token has expired: {str(e)}")
    except Exception as e:
        raise Exception(f"Token verification failed: {str(e)}")


# Initialize on module import
get_firebase_app()