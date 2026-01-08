# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from app.routes import onboarding, auth, cook, user, meal_items
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define security scheme for Swagger UI
security = HTTPBearer()

# Create FastAPI app
app = FastAPI(
    title="FoodEasy API",
    description="Backend API for FoodEasy - Meal Planning with Phone Authentication",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Override OpenAPI schema to include Bearer token authentication
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security scheme for Bearer token
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your Firebase ID token. Get it by calling POST /auth/verify-otp with your id_token."
        }
    }
    
    # Add security requirements to protected endpoints
    # Protected endpoints are those under /user, /cook paths (except /auth/verify-otp)
    protected_paths = ["/user", "/cook"]
    
    for path, path_item in openapi_schema.get("paths", {}).items():
        # Check if this is a protected path
        is_protected = any(path.startswith(protected) for protected in protected_paths)
        
        # Skip /auth/verify-otp (it's public)
        if path == "/auth/verify-otp":
            continue
            
        if is_protected:
            # Add security requirement to all methods (get, post, put, delete, etc.)
            for method in ["get", "post", "put", "delete", "patch"]:
                if method in path_item:
                    if "security" not in path_item[method]:
                        path_item[method]["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

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