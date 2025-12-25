# FoodEasy API Documentation

## Overview

FoodEasy is a meal planning application backend API built with FastAPI. The API provides endpoints for user authentication, onboarding, profile management, and cook management.

**Version:** 1.0.0  
**Base URL:** `http://localhost:8000` (development)  
**API Documentation:** Available at `/docs` (Swagger UI) and `/redoc` (ReDoc)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Root & Health Endpoints](#root--health-endpoints)
3. [Authentication Endpoints](#authentication-endpoints)
4. [Onboarding Endpoints](#onboarding-endpoints)
5. [User Management Endpoints](#user-management-endpoints)
6. [Cook Management Endpoints](#cook-management-endpoints)
7. [Error Handling](#error-handling)

---

## Authentication

Most endpoints require authentication using Firebase ID tokens. Include the token in the `Authorization` header:

```
Authorization: Bearer <firebase_id_token>
```

### Authentication Flow

1. User enters phone number in the mobile app
2. Firebase sends OTP to the phone number
3. User enters OTP, Firebase verifies it and returns an ID token
4. Mobile app calls `/auth/verify-otp` with the Firebase ID token
5. Backend verifies token, creates/retrieves user in Supabase
6. Returns `user_id` and phone number for authenticated user

### Token Format

- **Header:** `Authorization: Bearer <token>`
- **Token Type:** Firebase ID Token
- **Expiration:** Tokens expire after a set time (default: 1 hour / 3600 seconds)
- **Configurable:** Token expiration can be configured via `TOKEN_EXPIRATION_SECONDS` environment variable (max: 3600 seconds)

**Note:** Firebase ID tokens have a fixed maximum expiration of 1 hour (3600 seconds) that cannot be exceeded. This is a Firebase limitation.

---

## Root & Health Endpoints

### GET `/`

Get API information and available endpoints.

**Response:**
```json
{
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
```

---

### GET `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "foodeasy-backend",
  "features": ["onboarding", "phone-auth"]
}
```

---

## Authentication Endpoints

### POST `/auth/verify-otp`

Verify Firebase ID token after OTP verification and sync user with Supabase.

**Request Body:**
```json
{
  "id_token": "firebase_id_token_here"
}
```

**Response:**
```json
{
  "user_id": "uuid-here",
  "phone_number": "+1234567890",
  "is_new_user": true
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or expired token
- `500 Internal Server Error` - Server error

**Notes:**
- For returning users: Same phone number returns same `user_id`
- For new users: Creates new user profile with phone number only
- `is_new_user` indicates if this is the first time login

---

### GET `/auth/health`

Health check for authentication service.

**Response:**
```json
{
  "success": true,
  "service": "auth",
  "firebase": "connected",
  "supabase": "connected",
  "token_expiration_seconds": 3600
}
```

---

### POST `/auth/token-info`

Get detailed information about a Firebase ID token's expiration.

**Request Body:**
```json
{
  "id_token": "firebase_id_token_here"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "expires_at": "2024-01-01T01:00:00Z",
    "expires_in": 1800,
    "is_expired": false,
    "issued_at": "2024-01-01T00:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid token format

**Notes:**
- `expires_in` is in seconds (negative if expired)
- Useful for checking token expiration before making API calls
- Works even with expired tokens (to check expiration time)

---

### POST `/auth/refresh-token`

Get token refresh information and check if refresh is needed.

**Request Body:**
```json
{
  "id_token": "firebase_id_token_here"
}
```

**Response:**
```json
{
  "success": true,
  "needs_refresh": false,
  "data": {
    "expires_at": "2024-01-01T01:00:00Z",
    "expires_in": 1800,
    "is_expired": false,
    "issued_at": "2024-01-01T00:00:00Z"
  },
  "message": "Token refresh must be done client-side using Firebase SDK: await user.getIdToken(true)"
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid token

**Important Notes:**
- **Token refresh must be done client-side** using Firebase SDK
- This endpoint only validates the token and indicates if refresh is needed
- `needs_refresh` is `true` if token is expired or expires within 5 minutes
- Client should call `await user.getIdToken(true)` to force refresh

**Client-side refresh example:**
```javascript
// Check if refresh is needed
const response = await fetch('/auth/refresh-token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ id_token: currentToken })
});

const { needs_refresh } = await response.json();

if (needs_refresh) {
  // Force refresh on client side
  const freshToken = await user.getIdToken(true);
  await AsyncStorage.setItem('firebase_id_token', freshToken);
}
```

---

## Onboarding Endpoints

### GET `/onboarding`

Get all onboarding reference data in a single request.

**Response:**
```json
{
  "success": true,
  "data": {
    "goals": [
      {
        "id": "uuid",
        "name": "Weight Loss",
        "display_order": 1,
        "is_active": true
      }
    ],
    "dietary_patterns": [...],
    "dietary_restrictions": [...],
    "medical_restrictions": [...],
    "nutrition_preferences": [...],
    "spice_levels": [...],
    "cooking_oils": [...],
    "cuisines": [...],
    "meal_items": [
      {
        "onboarding_meal_item_name": "Idli",
        "onboarding_meal_item_id": "uuid",
        "onboarding_meal_item_image_url": "https://...",
        "meal_type_name": "Breakfast",
        "meal_type_id": "uuid",
        "can_vegetarian_eat": true,
        "can_eggetarian_eat": true,
        "can_carnitarian_eat": false,
        "can_omnitarian_eat": true,
        "can_vegan_eat": false
      }
    ]
  }
}
```

**Notes:**
- All data is fetched in parallel for optimal performance
- Only returns active items (`is_active = true`)
- Items are ordered by `display_order`

---

### GET `/onboarding/goals`

Get all available health and fitness goals.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Weight Loss",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/dietary-patterns`

Get all available dietary patterns (e.g., Vegetarian, Vegan, Non-Vegetarian).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Vegetarian",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/dietary-restrictions`

Get all available dietary restrictions (e.g., No Onion No Garlic, No Egg).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "No Onion No Garlic",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/medical-restrictions`

Get all available medical restrictions (e.g., Diabetes, Hypertension, PCOS).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Diabetes",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/nutrition-preferences`

Get all available nutrition preferences (e.g., High Protein, Low Carb, High Fiber).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "High Protein",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/spice-levels`

Get all available spice levels (e.g., Mild, Medium, Hot, Very Hot).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Medium",
      "display_order": 2,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/cooking-oils`

Get all available cooking oils (e.g., Olive Oil, Coconut Oil, Mustard Oil).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Olive Oil",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/cuisines`

Get all available cuisines (e.g., North Indian, South Indian, Chinese).

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "North Indian",
      "display_order": 1,
      "is_active": true
    }
  ]
}
```

---

### GET `/onboarding/meal-items`

Get all meal items with their meal types and dietary preferences.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "onboarding_meal_item_name": "Idli",
      "onboarding_meal_item_id": "uuid",
      "onboarding_meal_item_image_url": "https://...",
      "meal_type_name": "Breakfast",
      "meal_type_id": "uuid",
      "can_vegetarian_eat": true,
      "can_eggetarian_eat": true,
      "can_carnitarian_eat": false,
      "can_omnitarian_eat": true,
      "can_vegan_eat": false
    }
  ]
}
```

**Notes:**
- Only returns active meal items (`is_active = true`)
- Each meal item includes dietary compatibility flags

---

## User Management Endpoints

All user endpoints require authentication.

### GET `/user/{user_id}`

Get complete user profile including all data and metadata.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "firebase_uid": "firebase-uid",
    "phone_number": "+1234567890",
    "full_name": "John Doe",
    "created_at": "2024-01-01T00:00:00Z",
    "last_login": "2024-01-01T00:00:00Z",
    "metadata": {
      "age": 28,
      "gender": "male",
      "total_household_adults": 2,
      "total_household_children": 1,
      "onboarding_completed": true,
      "onboarding_completed_at": "2024-01-01T00:00:00Z",
      "goals": ["Weight Loss", "Muscle Gain"],
      "dietary_pattern": "Vegetarian",
      "medical_restrictions": ["Diabetes"],
      "nutrition_preferences": ["High Protein"],
      "dietary_restrictions": ["No Onion No Garlic"],
      "spice_level": "Medium",
      "cooking_oil_preferences": ["Olive Oil", "Coconut Oil"],
      "cuisines_preferences": ["North Indian", "South Indian"],
      "breakfast_preferences": ["Idli", "Poha"],
      "lunch_preferences": ["Dal Rice"],
      "snacks_preferences": ["Samosa"],
      "dinner_preferences": ["Roti Sabzi"],
      "extra_input": "I prefer early dinner around 7 PM"
    }
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - User not found
- `500 Internal Server Error` - Server error

**Notes:**
- Age, gender, household info, onboarding status, and preferences are stored in the `metadata` JSONB column
- Only `full_name`, `phone_number`, `created_at`, and `last_login` are direct columns

---

### PUT `/user/{user_id}/profile`

Update user profile including basic fields and metadata.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Request Body:**
```json
{
  "full_name": "John Doe",
  "age": 28,
  "gender": "male",
  "total_household_adults": 2,
  "total_household_children": 1,
  "metadata": {
    "preferences": {
      "theme": "dark",
      "notifications": true
    },
    "custom_field": "custom_value"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "User profile updated successfully",
  "data": {
    "id": "uuid",
    "full_name": "John Doe",
    "metadata": {
      "age": 28,
      "gender": "male",
      "total_household_adults": 2,
      "total_household_children": 1,
      "preferences": {
        "theme": "dark",
        "notifications": true
      },
      "custom_field": "custom_value"
    }
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `500 Internal Server Error` - Server error

**Notes:**
- `full_name` is stored as a direct column
- `age`, `gender`, `total_household_adults`, `total_household_children` are stored in metadata
- Custom metadata is merged with existing metadata (not replaced)
- Protected fields: `id`, `firebase_uid`, `phone_number`, `created_at` cannot be updated

---

### PUT `/user/{user_id}/onboarding`

Save complete onboarding data for a user.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Request Body:**
```json
{
  "full_name": "John Doe",
  "age": 28,
  "gender": "male",
  "total_household_adults": 2,
  "total_household_children": 1,
  "goals": ["Weight Loss", "Muscle Gain"],
  "medical_restrictions": ["Diabetes"],
  "dietary_pattern": "Vegetarian",
  "nutrition_preferences": ["High Protein"],
  "dietary_restrictions": ["No Onion No Garlic"],
  "spice_level": "Medium",
  "cooking_oil_preferences": ["Olive Oil", "Coconut Oil"],
  "cuisines_preferences": ["North Indian", "South Indian"],
  "breakfast_preferences": ["Idli", "Poha"],
  "lunch_preferences": ["Dal Rice"],
  "snacks_preferences": ["Samosa"],
  "dinner_preferences": ["Roti Sabzi"],
  "extra_input": "I prefer early dinner around 7 PM"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Onboarding data saved successfully",
  "data": {
    "id": "uuid",
    "full_name": "John Doe",
    "metadata": {
      "age": 28,
      "gender": "male",
      "total_household_adults": 2,
      "total_household_children": 1,
      "goals": ["Weight Loss", "Muscle Gain"],
      "dietary_pattern": "Vegetarian",
      "onboarding_completed": true,
      "onboarding_completed_at": "2024-01-01T00:00:00Z"
    }
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - User not found
- `500 Internal Server Error` - Server error

**Important Notes:**
- **Send actual TEXT values (names), NOT IDs**
- Example: ✅ `"goals": ["Weight Loss", "Muscle Gain"]`
- Example: ❌ `"goals": ["goal_id_1", "goal_id_2"]`
- `full_name` is stored as a direct column
- All other onboarding data is stored in the `metadata` JSONB column
- Setting onboarding data automatically marks `onboarding_completed` as `true`

---

### GET `/user/{user_id}/onboarding-status`

Check if user has completed the onboarding process.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "onboarding_completed": true,
    "onboarding_completed_at": "2024-01-01T00:00:00Z",
    "has_name": true
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - User not found
- `500 Internal Server Error` - Server error

**Notes:**
- Use this endpoint to determine if user needs to complete onboarding flow
- `onboarding_completed_at` is only present if onboarding is completed

---

## Cook Management Endpoints

All cook endpoints require authentication.

### POST `/cook/user/{user_id}/cooks`

Add a new cook for a user.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Request Body:**
```json
{
  "name": "Ramesh Kumar",
  "phone_number": "9876543210",
  "languages_known": ["Hindi", "English"],
  "has_smart_phone": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Cook added successfully",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "name": "Ramesh Kumar",
    "phone_number": "9876543210",
    "languages_known": ["Hindi", "English"],
    "has_smart_phone": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

**Status Codes:**
- `201 Created` - Success
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `500 Internal Server Error` - Server error

---

### GET `/cook/user/{user_id}/cooks`

Get all cooks associated with a user.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "name": "Ramesh Kumar",
      "phone_number": "9876543210",
      "languages_known": ["Hindi", "English"],
      "has_smart_phone": true,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "count": 1
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `500 Internal Server Error` - Server error

---

### GET `/cook/user/{user_id}/cooks/{cook_id}`

Get details of a specific cook.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "name": "Ramesh Kumar",
    "phone_number": "9876543210",
    "languages_known": ["Hindi", "English"],
    "has_smart_phone": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - Cook not found
- `500 Internal Server Error` - Server error

---

### PUT `/cook/user/{user_id}/cooks/{cook_id}`

Update information for a specific cook.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Request Body:**
```json
{
  "name": "Ramesh Kumar",
  "languages_known": ["Hindi", "English", "Tamil"],
  "has_smart_phone": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Cook updated successfully",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "name": "Ramesh Kumar",
    "phone_number": "9876543210",
    "languages_known": ["Hindi", "English", "Tamil"],
    "has_smart_phone": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - Cook not found
- `500 Internal Server Error` - Server error

**Notes:**
- All fields are optional in the request body
- Only provided fields will be updated

---

### DELETE `/cook/user/{user_id}/cooks/{cook_id}`

Remove a cook from the user's list.

**Headers:**
```
Authorization: Bearer <firebase_id_token>
```

**Response:**
```json
{
  "success": true,
  "message": "Cook deleted successfully"
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Invalid or missing token
- `403 Forbidden` - User trying to access another user's data
- `404 Not Found` - Cook not found
- `500 Internal Server Error` - Server error

---

## Error Handling

The API uses standard HTTP status codes and returns error responses in the following format:

```json
{
  "detail": "Error message description"
}
```

### Common Status Codes

- **200 OK** - Request successful
- **201 Created** - Resource created successfully
- **400 Bad Request** - Invalid request data or parameters
- **401 Unauthorized** - Authentication required or token invalid/expired
- **403 Forbidden** - User doesn't have permission to access the resource
- **404 Not Found** - Resource not found
- **500 Internal Server Error** - Server error

### Authentication Errors

When authentication fails, the API returns:

```json
{
  "detail": "Invalid token. Please login again."
}
```

Common authentication error messages:
- `"Authorization header is required"` - Missing Authorization header
- `"Invalid authorization header format. Expected: Bearer <token>"` - Incorrect header format
- `"Invalid token. Please login again."` - Invalid or malformed token
- `"Token expired. Please login again."` - Token has expired
- `"Token expired. Please request new OTP."` - Token expired during OTP verification
- `"User not found. Please complete registration first."` - User doesn't exist in Supabase

**Handling Token Expiration:**
1. Check token expiration using `POST /auth/token-info` before making API calls
2. If token is expired or about to expire, refresh it client-side using Firebase SDK
3. Use `POST /auth/refresh-token` to check if refresh is needed
4. Client-side refresh: `await user.getIdToken(true)` to force refresh

### Validation Errors

Validation errors occur when request data doesn't meet requirements:

```json
{
  "detail": "Field validation error message"
}
```

Example:
```json
{
  "detail": "age: ensure this value is greater than or equal to 1"
}
```

---

## Data Models

### User Profile Structure

User profiles store data in two ways:

1. **Direct Columns:**
   - `id` (UUID) - Primary key
   - `firebase_uid` (String) - Firebase user ID
   - `phone_number` (String) - User's phone number
   - `full_name` (String, nullable) - User's full name
   - `created_at` (Timestamp) - Account creation time
   - `last_login` (Timestamp, nullable) - Last login time

2. **Metadata JSONB Column:**
   - `age` (Integer)
   - `gender` (String)
   - `total_household_adults` (Integer)
   - `total_household_children` (Integer)
   - `onboarding_completed` (Boolean)
   - `onboarding_completed_at` (Timestamp)
   - `goals` (Array of Strings)
   - `dietary_pattern` (String)
   - `medical_restrictions` (Array of Strings)
   - `nutrition_preferences` (Array of Strings)
   - `dietary_restrictions` (Array of Strings)
   - `spice_level` (String)
   - `cooking_oil_preferences` (Array of Strings)
   - `cuisines_preferences` (Array of Strings)
   - `breakfast_preferences` (Array of Strings)
   - `lunch_preferences` (Array of Strings)
   - `snacks_preferences` (Array of Strings)
   - `dinner_preferences` (Array of Strings)
   - `extra_input` (String)
   - Any custom key-value pairs

### Cook Structure

- `id` (UUID) - Primary key
- `user_id` (UUID) - Foreign key to user_profiles
- `name` (String) - Cook's full name
- `phone_number` (String) - Cook's phone number
- `languages_known` (Array of Strings) - Languages the cook knows
- `has_smart_phone` (Boolean) - Whether cook has a smartphone
- `created_at` (Timestamp) - Record creation time

---

## Rate Limiting

Currently, there are no rate limits implemented. Consider implementing rate limiting in production.

---

## CORS

CORS is configured to allow requests from specified origins. The default configuration allows all origins (`*`). Configure `CORS_ORIGINS` environment variable to restrict origins in production.

---

## Environment Variables

Required environment variables:

- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `FIREBASE_CREDENTIALS_PATH` - Path to Firebase credentials JSON file
- `CORS_ORIGINS` - Comma-separated list of allowed CORS origins (optional, defaults to "*")

Optional environment variables:

- `TOKEN_EXPIRATION_SECONDS` - Token expiration time in seconds (default: 3600, max: 3600)
  - Note: Firebase ID tokens have a fixed maximum of 1 hour (3600 seconds)
  - This setting applies to custom tokens created by the backend
  - Client-issued Firebase ID tokens always expire after 1 hour

---

## Support

For issues or questions, please refer to the project repository or contact the development team.

---

**Last Updated:** 2024

