# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import onboarding, auth  # Import auth
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="FoodEasy API",
    description="Backend API for FoodEasy - Meal Planning with Phone Authentication",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
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
app.include_router(auth.router)  # NEW: Auth routes

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
            "auth": "/auth"
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