# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from app.routes import onboarding, auth, cook, user, meal_items, meal_plan, grocery, meal_messaging
from app.test.routes import test_meal_generation, test_user_creation
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define security scheme for Swagger UI
security = HTTPBearer()

# Create FastAPI app
app = FastAPI(
    title="FoodEasy API",
    description="Backend API for FoodEasy",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Override OpenAPI schema to include Bearer token authentication
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    try:
        from fastapi.openapi.utils import get_openapi
        import logging
        
        logger = logging.getLogger(__name__)
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Ensure components section exists
        if "components" not in openapi_schema:
            openapi_schema["components"] = {}
        
        # Add security scheme for Bearer token
        openapi_schema["components"]["securitySchemes"] = {
            "Bearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Backend JWT from POST /auth/verify-otp (phone_number + otp_code)."
            }
        }
        
        # Add security requirements to protected endpoints
        # Protected endpoints are those under /user, /cook, /meal-plan, /grocery paths (except /auth/verify-otp)
        protected_paths = ["/user", "/cook", "/meal-plan", "/meal-messaging", "/grocery"]
        
        for path, path_item in openapi_schema.get("paths", {}).items():
            # Check if this is a protected path
            is_protected = any(path.startswith(protected) for protected in protected_paths)
            
            # Skip public auth endpoints
            if path in ("/auth/verify-otp", "/auth/send-otp"):
                continue
            # Skip user hard-delete (no auth)
            if "/hard-delete" in path:
                continue
                
            if is_protected:
                # Add security requirement to all methods (get, post, put, delete, etc.)
                for method in ["get", "post", "put", "delete", "patch"]:
                    if method in path_item:
                        if "security" not in path_item[method]:
                            path_item[method]["security"] = [{"Bearer": []}]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating OpenAPI schema: {str(e)}", exc_info=True)
        # Fallback to default OpenAPI schema if custom generation fails
        from fastapi.openapi.utils import get_openapi
        return get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

# CORS middleware (allow frontend to access API)
cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins != "*":
    cors_origins = [origin.strip() for origin in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if isinstance(cors_origins, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(onboarding.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(cook.router)
app.include_router(meal_items.router)
app.include_router(meal_plan.router)
app.include_router(grocery.router)
app.include_router(meal_messaging.router)

# Include test routers
app.include_router(test_meal_generation.router)
app.include_router(test_user_creation.router)

# Set custom OpenAPI schema after all routers are included
app.openapi = custom_openapi

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to FoodEasy API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "onboarding": "/onboarding",
            "auth": "/auth",
            "user": "/user"
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "foodeasy-backend",
        "features": ["onboarding", "phone-auth"]
    }

# Run with: uvicorn app.main:app --reload
if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment variables
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug
    )