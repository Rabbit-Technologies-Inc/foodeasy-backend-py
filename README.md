# FoodEasy Backend

A FastAPI-based backend for a meal planning application with Firebase authentication, Supabase database, and various AI-powered features.

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Development Workflow](#development-workflow)

---

## Project Overview

FoodEasy is a comprehensive meal planning application backend that provides:
- User authentication via Firebase (phone-based OTP)
- Meal planning and customization
- Dietary preference management
- Grocery list generation
- Cook management
- Meal reminders and notifications
- AI-powered meal suggestions

---

## Tech Stack

- **FastAPI** - Modern Python web framework
- **Supabase** - PostgreSQL database and backend services
- **Firebase Admin** - Authentication and user management
- **Twilio** - SMS and phone services
- **OpenAI** - AI-powered features
- **ElevenLabs** - Text-to-speech services
- **Uvicorn** - ASGI server

---

## Prerequisites

### 1. Python Installation

Ensure you have Python 3.9 or higher installed:

```bash
python3 --version
```

If you need to install or upgrade Python, visit [python.org](https://www.python.org/downloads/).

### 2. Required External Services

You'll need accounts and credentials for:
- **Supabase** - [supabase.com](https://supabase.com)
- **Firebase** - [firebase.google.com](https://firebase.google.com)
- **Twilio** (optional) - [twilio.com](https://www.twilio.com)
- **OpenAI** (optional) - [openai.com](https://openai.com)
- **ElevenLabs** (optional) - [elevenlabs.io](https://elevenlabs.io)

---

## Local Setup

### Step 1: Clone the Repository

```bash
cd /path/to/your/projects
git clone <repository-url>
cd foodeasy-backend
```

### Step 2: Create Virtual Environment

Create and activate a Python virtual environment to isolate dependencies:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### Step 3: Install Dependencies

Install all required Python packages:

```bash
# Upgrade pip first
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt
```

This will install all 72+ packages including FastAPI, Firebase Admin, Supabase, and more.

### Step 4: Configure Environment Variables

Create your `.env` file from the example:

```bash
cp .env.example .env
```

Edit the `.env` file with your actual credentials:

```env
# Supabase Configuration
# Get these from your Supabase project dashboard
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# CORS Configuration
# Use "*" to allow all origins, or specify comma-separated origins
CORS_ORIGINS=*

# Firebase Configuration
# Method 1: File path to Firebase credentials JSON
FIREBASE_CREDENTIALS_PATH=./path/to/your-firebase-credentials.json

# OR Method 2: Direct JSON content (useful for deployment)
# FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}

# Optional: Token expiration (max 3600 seconds / 1 hour)
TOKEN_EXPIRATION_SECONDS=3600
```

### Step 5: Setup Firebase Credentials

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (or create a new one)
3. Navigate to **Project Settings** → **Service Accounts**
4. Click **"Generate New Private Key"**
5. Download the JSON file
6. Save it to your project directory (e.g., `firebase-credentials.json`)
7. Update `FIREBASE_CREDENTIALS_PATH` in your `.env` file with the correct path

**Security Note:** Never commit the Firebase credentials JSON file to git. It's already in `.gitignore`.

### Step 6: Setup Supabase

1. Create a project on [Supabase](https://supabase.com)
2. Go to **Project Settings** → **API**
3. Copy the following values to your `.env` file:
   - Project URL → `SUPABASE_URL`
   - anon public key → `SUPABASE_KEY`
   - service_role key → `SUPABASE_SERVICE_ROLE_KEY`

**Note:** Ensure your Supabase database tables are properly set up according to your schema.

---

## Running the Application

You have several options to start the server:

### Option 1: Using Python Directly

```bash
python3 app/main.py
```

### Option 2: Using Uvicorn (Recommended for Development)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The `--reload` flag enables auto-restart on code changes.

### Option 3: Using Python Module

```bash
python3 -m app.main
```

### Successful Startup

When the server starts successfully, you should see:

```
✓ Firebase Admin SDK initialized successfully
✓ Firebase project_id: your-project-id
✓ Token expiration configured: 3600 seconds (60 minutes)
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process using StatReload
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

---

## API Documentation

Once the server is running, access the interactive API documentation:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
  - Interactive API explorer with "Try it out" functionality
  - Test all endpoints directly from the browser

- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
  - Clean, readable API documentation
  - Better for reference and sharing

- **Root Endpoint**: [http://localhost:8000/](http://localhost:8000/)
  - API information and available endpoints

- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
  - Server health status

### Testing the API

#### Using curl:

```bash
# Health check
curl http://localhost:8000/health

# Root endpoint
curl http://localhost:8000/
```

#### Using Swagger UI:

1. Navigate to http://localhost:8000/docs
2. Click on any endpoint to expand it
3. Click "Try it out"
4. Fill in required parameters
5. Click "Execute"

For detailed API documentation, see [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md).

---

## Project Structure

```
foodeasy-backend/
├── app/
│   ├── main.py                 # Application entry point & FastAPI app setup
│   ├── routes/                 # API route handlers
│   │   ├── auth.py            # Authentication endpoints
│   │   ├── user.py            # User management endpoints
│   │   ├── onboarding.py      # Onboarding data endpoints
│   │   ├── meal_plan.py       # Meal planning endpoints
│   │   ├── meal_items.py      # Meal items endpoints
│   │   ├── grocery.py         # Grocery list endpoints
│   │   └── meal_messaging.py  # Meal notifications
│   ├── services/              # Business logic & external services
│   │   ├── firebase_service.py # Firebase authentication
│   │   ├── supabase_service.py # Database operations
│   │   └── ...
│   ├── dependencies/          # FastAPI dependencies
│   │   └── auth.py            # Authentication middleware
│   └── test/                  # Test endpoints
│       └── routes/
├── cron_jobs/                 # Scheduled background tasks
│   ├── send_meal_reminders.py
│   ├── send_soaking_reminders.py
│   └── manage_meal_plans.py
├── scripts/                   # Utility scripts
│   ├── test_translation.py
│   └── test_tts.py
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
├── .env                      # Your environment variables (create this)
├── .gitignore
├── API_DOCUMENTATION.md      # Detailed API documentation
├── PHONE_AUTH_INTEGRATION.md # Phone authentication guide
└── README.md                 # This file
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. Firebase Credentials Not Found

**Error:** `Firebase credentials file not found`

**Solution:**
- Verify the path in `FIREBASE_CREDENTIALS_PATH` is correct
- Use absolute path if relative path doesn't work
- Or use `FIREBASE_CREDENTIALS_JSON` with the full JSON content

#### 2. Module Not Found Errors

**Error:** `ModuleNotFoundError: No module named 'xxx'`

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### 3. Port Already in Use

**Error:** `Address already in use`

**Solution:**
```bash
# Option 1: Change port in .env
API_PORT=8001

# Option 2: Kill process using port 8000
lsof -ti:8000 | xargs kill -9
```

#### 4. Supabase Connection Issues

**Error:** Connection errors to Supabase

**Solution:**
- Verify `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` are correct
- Check if your Supabase project is active
- Ensure your IP is not blocked by Supabase

#### 5. Import Errors

**Error:** `ImportError` or circular import issues

**Solution:**
- Ensure you're running from the project root directory
- Check that `__init__.py` files exist in package directories

#### 6. Token Verification Fails

**Error:** `Invalid token` or `Token expired`

**Solution:**
- Verify Firebase project IDs match between frontend and backend
- Check token hasn't expired (1-hour limit)
- Ensure Firebase credentials are for the correct project

---

## Development Workflow

### Daily Development

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Start development server with auto-reload
uvicorn app.main:app --reload

# 3. Make your changes

# 4. Test via Swagger UI at http://localhost:8000/docs

# 5. When done, deactivate virtual environment
deactivate
```

### Useful Commands

```bash
# List installed packages
pip list

# Check for outdated packages
pip list --outdated

# Update a specific package
pip install --upgrade package-name

# Freeze current dependencies
pip freeze > requirements.txt

# Run Python script
python3 scripts/test_translation.py
```

### Code Quality

```bash
# Format code with black (if installed)
black app/

# Lint with flake8 (if installed)
flake8 app/

# Type checking with mypy (if installed)
mypy app/
```

---

## Environment Variables Reference

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `SUPABASE_URL` | Yes | Your Supabase project URL | - |
| `SUPABASE_KEY` | Yes | Supabase anon public key | - |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key | - |
| `FIREBASE_CREDENTIALS_PATH` | Yes* | Path to Firebase credentials JSON | - |
| `FIREBASE_CREDENTIALS_JSON` | Yes* | Firebase credentials as JSON string | - |
| `API_HOST` | No | Server host address | `0.0.0.0` |
| `API_PORT` | No | Server port | `8000` |
| `DEBUG` | No | Enable debug mode | `True` |
| `CORS_ORIGINS` | No | Allowed CORS origins | `*` |
| `TOKEN_EXPIRATION_SECONDS` | No | Token expiration time | `3600` |

*Either `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` is required, not both.

---

## Additional Resources

- **API Documentation**: [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md) - Comprehensive API reference
- **Phone Auth Guide**: [`PHONE_AUTH_INTEGRATION.md`](./PHONE_AUTH_INTEGRATION.md) - Phone authentication setup
- **FastAPI Docs**: [fastapi.tiangolo.com](https://fastapi.tiangolo.com)
- **Supabase Docs**: [supabase.com/docs](https://supabase.com/docs)
- **Firebase Docs**: [firebase.google.com/docs](https://firebase.google.com/docs)

---

## Support & Contributing

For issues, questions, or contributions:
1. Check existing issues in the repository
2. Review the API documentation
3. Contact the development team

---

## License

[Add your license information here]

---

**Last Updated:** February 2026