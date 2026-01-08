# app/services/firebase_admin.py

import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv
import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

load_dotenv()

# Get Firebase credentials - support both file path and JSON content from .env
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")

# Token expiration configuration (in seconds)
# Default: 3600 seconds (1 hour) - Firebase ID tokens have fixed 1-hour expiration
# Custom tokens can have expiration up to 1 hour (3600 seconds) max
TOKEN_EXPIRATION_SECONDS = int(os.getenv("TOKEN_EXPIRATION_SECONDS", "3600"))

# Maximum allowed token expiration (Firebase limit: 1 hour)
MAX_TOKEN_EXPIRATION_SECONDS = 3600

# Validate token expiration setting
if TOKEN_EXPIRATION_SECONDS > MAX_TOKEN_EXPIRATION_SECONDS:
    print(f"Warning: TOKEN_EXPIRATION_SECONDS ({TOKEN_EXPIRATION_SECONDS}) exceeds Firebase limit ({MAX_TOKEN_EXPIRATION_SECONDS}). Using {MAX_TOKEN_EXPIRATION_SECONDS}.")
    TOKEN_EXPIRATION_SECONDS = MAX_TOKEN_EXPIRATION_SECONDS

# Initialize credentials - support both file path and JSON content
FIREBASE_CREDENTIALS_DICT: Optional[Dict[str, Any]] = None

if FIREBASE_CREDENTIALS_JSON:
    # Use JSON content from environment variable
    try:
        # Parse JSON to validate it's valid
        FIREBASE_CREDENTIALS_DICT = json.loads(FIREBASE_CREDENTIALS_JSON)
        FIREBASE_CREDENTIALS_PATH = None  # Clear path since we're using JSON
    except json.JSONDecodeError as e:
        raise ValueError(
            f"FIREBASE_CREDENTIALS_JSON contains invalid JSON: {str(e)}. "
            "Please ensure the JSON is properly formatted."
        )
elif FIREBASE_CREDENTIALS_PATH:
    # Use file path
    if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
        raise ValueError(
            f"Firebase credentials file not found at: {FIREBASE_CREDENTIALS_PATH}. "
            "Please download your service account key from Firebase Console and place it in the project root, "
            "or set FIREBASE_CREDENTIALS_JSON with the JSON content in your .env file."
        )
else:
    raise ValueError(
        "Firebase credentials not configured. "
        "Please set either FIREBASE_CREDENTIALS_PATH (file path) or FIREBASE_CREDENTIALS_JSON (JSON content) in your .env file."
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
            # Use JSON dict if available, otherwise use file path
            if FIREBASE_CREDENTIALS_DICT:
                cred = credentials.Certificate(FIREBASE_CREDENTIALS_DICT)
            else:
                cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            
            _firebase_app = firebase_admin.initialize_app(cred)
            # Get project_id from credentials
            if FIREBASE_CREDENTIALS_DICT:
                project_id = FIREBASE_CREDENTIALS_DICT.get('project_id', 'unknown')
            elif FIREBASE_CREDENTIALS_PATH:
                import json
                with open(FIREBASE_CREDENTIALS_PATH, 'r') as f:
                    cred_data = json.load(f)
                    project_id = cred_data.get('project_id', 'unknown')
            else:
                project_id = 'unknown'
            print(f"✓ Firebase Admin SDK initialized successfully")
            print(f"✓ Firebase project_id: {project_id}")
            print(f"✓ Token expiration configured: {TOKEN_EXPIRATION_SECONDS} seconds ({TOKEN_EXPIRATION_SECONDS // 60} minutes)")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Firebase Admin SDK: {str(e)}") from e
    
    return _firebase_app


def verify_firebase_token(id_token: str, check_expiration: bool = True) -> dict:
    """
    Verify Firebase ID token and return decoded token data.
    
    Args:
        id_token: Firebase ID token from React Native client
        check_expiration: If True, explicitly check token expiration time
        
    Returns:
        dict: Decoded token containing uid, phone_number, exp, iat, etc.
        
    Raises:
        auth.InvalidIdTokenError: If token is invalid
        auth.ExpiredIdTokenError: If token has expired
    """
    if not id_token or not isinstance(id_token, str) or len(id_token.strip()) == 0:
        raise ValueError("ID token is required and must be a non-empty string")
    
    get_firebase_app()  # Ensure Firebase is initialized
    
    try:
        # Get project_id from credentials
        if FIREBASE_CREDENTIALS_DICT:
            backend_project_id = FIREBASE_CREDENTIALS_DICT.get('project_id', 'unknown')
        elif FIREBASE_CREDENTIALS_PATH:
            import json
            with open(FIREBASE_CREDENTIALS_PATH, 'r') as f:
                cred_data = json.load(f)
                backend_project_id = cred_data.get('project_id', 'unknown')
        else:
            backend_project_id = 'unknown'
        
        print(f"Verifying token with Firebase project: {backend_project_id}")
        
        decoded_token = auth.verify_id_token(id_token, check_revoked=False)
        
        # Log decoded token info (without sensitive data)
        token_project_id = decoded_token.get('aud', 'unknown')
        print(f"Token verified. Token project_id (aud): {token_project_id}, Backend project_id: {backend_project_id}")
        
        # Check if project IDs match
        if token_project_id != backend_project_id:
            print(f"WARNING: Project ID mismatch! Token is from '{token_project_id}' but backend is configured for '{backend_project_id}'")
            raise auth.InvalidIdTokenError(
                f"Token project mismatch. Token is from project '{token_project_id}' but backend expects '{backend_project_id}'. "
                "Make sure your React Native app and backend are using the same Firebase project."
            )
        
        # Additional expiration check if requested
        if check_expiration:
            exp = decoded_token.get('exp')
            if exp:
                expiration_time = datetime.fromtimestamp(exp)
                current_time = datetime.utcnow()
                if expiration_time <= current_time:
                    raise auth.ExpiredIdTokenError("Token has expired")
        
        return decoded_token
    except auth.InvalidIdTokenError as e:
        print(f"InvalidIdTokenError in verify_firebase_token: {str(e)}")
        raise
    except auth.ExpiredIdTokenError as e:
        print(f"ExpiredIdTokenError in verify_firebase_token: {str(e)}")
        raise
    except Exception as e:
        import traceback
        print(f"Unexpected error in verify_firebase_token: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise Exception(f"Token verification failed: {str(e)}")


def get_token_expiration_info(decoded_token: dict) -> Dict[str, Any]:
    """
    Get token expiration information from decoded token.
    
    Args:
        decoded_token: Decoded Firebase token dictionary
        
    Returns:
        dict: Token expiration information including:
            - expires_at: ISO timestamp when token expires
            - expires_in: Seconds until expiration
            - is_expired: Boolean indicating if token is expired
            - issued_at: ISO timestamp when token was issued
    """
    exp = decoded_token.get('exp')
    iat = decoded_token.get('iat')
    
    if not exp:
        return {
            "expires_at": None,
            "expires_in": None,
            "is_expired": None,
            "issued_at": None
        }
    
    expiration_time = datetime.fromtimestamp(exp)
    issued_time = datetime.fromtimestamp(iat) if iat else None
    current_time = datetime.utcnow()
    
    expires_in_seconds = int((expiration_time - current_time).total_seconds())
    
    return {
        "expires_at": expiration_time.isoformat() + "Z",
        "expires_in": expires_in_seconds,
        "is_expired": expires_in_seconds <= 0,
        "issued_at": issued_time.isoformat() + "Z" if issued_time else None
    }


def create_custom_token(uid: str, additional_claims: Optional[Dict[str, Any]] = None, expiration_seconds: Optional[int] = None) -> str:
    """
    Create a custom Firebase token with configurable expiration.
    
    Note: Custom tokens can have expiration up to 1 hour (3600 seconds) maximum.
    Firebase ID tokens (from client) have fixed 1-hour expiration that cannot be changed.
    
    Args:
        uid: Firebase user ID
        additional_claims: Optional custom claims to include in token
        expiration_seconds: Token expiration in seconds (max 3600, default from TOKEN_EXPIRATION_SECONDS)
        
    Returns:
        str: Custom token that can be exchanged for an ID token on the client
        
    Raises:
        ValueError: If expiration_seconds exceeds maximum allowed
    """
    get_firebase_app()  # Ensure Firebase is initialized
    
    # Use configured expiration or provided value
    exp_seconds = expiration_seconds if expiration_seconds is not None else TOKEN_EXPIRATION_SECONDS
    
    # Validate expiration
    if exp_seconds > MAX_TOKEN_EXPIRATION_SECONDS:
        raise ValueError(f"Token expiration cannot exceed {MAX_TOKEN_EXPIRATION_SECONDS} seconds (1 hour)")
    
    if exp_seconds <= 0:
        raise ValueError("Token expiration must be greater than 0")
    
    # Calculate expiration time
    expiration_time = datetime.utcnow() + timedelta(seconds=exp_seconds)
    
    # Prepare claims
    claims = additional_claims or {}
    claims['exp'] = int(expiration_time.timestamp())
    
    try:
        custom_token = auth.create_custom_token(uid, claims)
        return custom_token
    except Exception as e:
        raise Exception(f"Failed to create custom token: {str(e)}")


# Initialize on module import
get_firebase_app()