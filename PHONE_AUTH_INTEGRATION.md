# Phone OTP Authentication Integration Guide

## Overview

This document provides instructions for integrating Firebase Phone OTP authentication with the FoodEasy backend API.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Firebase Setup Requirements](#firebase-setup-requirements)
3. [Authentication Flow](#authentication-flow)
4. [API Endpoints](#api-endpoints)
5. [React Native Integration Steps](#react-native-integration-steps)
6. [Error Handling](#error-handling)
7. [Testing](#testing)

---

## Architecture Overview
```
┌─────────────────┐
│  React Native   │  1. User enters phone (9876543210)
│      App        │  2. Firebase sends OTP SMS
└────────┬────────┘  3. User enters OTP (123456)
         │           4. Firebase verifies OTP
         │           5. Firebase returns ID Token
         ▼
┌─────────────────┐
│  Firebase Auth  │  Handles OTP generation, SMS, verification
└────────┬────────┘
         │
         │ POST /auth/verify-otp
         │ { "id_token": "..." }
         ▼
┌─────────────────┐
│  Backend API    │  Verifies token, returns user_id
└────────┬────────┘
         │
         │ Response: { "user_id": "...", "is_new_user": true }
         ▼
┌─────────────────┐
│  React Native   │  Stores user_id, navigates to Home/Name screen
└─────────────────┘
```

**Key Points:**
- Firebase handles ALL OTP logic (generation, SMS sending, verification)
- Backend only verifies Firebase token and manages user data
- No SMS provider integration needed on your side

---

## Firebase Setup Requirements

### What You Need to Do:

1. **Create Firebase Project** (if not done)
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Create/select your project

2. **Enable Phone Authentication**
   - Firebase Console → Authentication → Sign-in method
   - Enable "Phone" provider
   - Save

3. **Register Your React Native App**

   **For Android:**
   - Add Android app in Firebase Console
   - Download `google-services.json`
   - Place in `android/app/` directory

   **For iOS:**
   - Add iOS app in Firebase Console
   - Download `GoogleService-Info.plist`
   - Add to Xcode project

4. **Get Firebase Config**
   - Project Settings → General → Your apps
   - Copy the config object (needed for initialization)

5. **(Optional) Add Test Phone Numbers**
   - Authentication → Settings → Phone numbers for testing
   - Add: `+919876543210` → OTP: `123456`
   - Use these for testing without SMS charges

---

## Authentication Flow

### Complete User Journey
```
Step 1: Login Screen
├─ User enters: 9876543210
└─ Click "Send OTP"
    ↓
Step 2: Firebase sends SMS
├─ User receives: "Your OTP is 123456"
└─ OTP valid for 10 minutes
    ↓
Step 3: OTP Verification Screen
├─ User enters: 123456
├─ Firebase verifies OTP
└─ If correct → Firebase returns ID Token
    ↓
Step 4: Call Backend API
├─ POST /auth/verify-otp with ID token
└─ Backend returns: { user_id, is_new_user }
    ↓
Step 5: Store user_id
└─ Save to AsyncStorage
    ↓
Step 6: Navigate based on is_new_user
├─ If is_new_user = true → Name Input Screen
└─ If is_new_user = false → Home Screen
    ↓
Step 7: (For new users only) Name Input
├─ User enters: "Nik Kumar"
├─ PUT /auth/user/{user_id}/profile
└─ Navigate to Home Screen
```

### Resend OTP Flow
```
User on OTP Screen
├─ Click "Resend OTP"
├─ Call Firebase sendOTP again (same as Step 1)
├─ Firebase sends NEW OTP
├─ Old OTP becomes invalid
└─ User enters new OTP
```

---

## API Endpoints

### Base URL
```
Development: http://localhost:8000
Production: https://api.foodeasy.com
```

---

### 1. Verify OTP

**Endpoint:** `POST /auth/verify-otp`

**Description:** Verify Firebase ID token and get user_id

**When to call:** After Firebase successfully verifies the OTP

**Request Body:**
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjFlOWdkazcifQ..."
}
```

**Success Response (200):**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "phone_number": "+919876543210",
  "is_new_user": true
}
```

**What to do after:**
- Store `user_id` in AsyncStorage
- If `is_new_user = true` → Navigate to Name Input Screen
- If `is_new_user = false` → Navigate to Home Screen

**Error Responses:**
- `400` - Missing id_token in request
- `401` - Invalid or expired token (ask user to login again)
- `500` - Server error (show generic error message)

---

### 2. Update User Profile

**Endpoint:** `PUT /auth/user/{user_id}/profile`

**Description:** Add/update user's name

**When to call:** After new user login, when user enters their name

**Request Body:**
```json
{
  "full_name": "Nik Kumar"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "firebase_uid": "abc123xyz",
    "phone_number": "+919876543210",
    "full_name": "Nik Kumar",
    "created_at": "2025-01-01T00:00:00.000Z",
    "last_login": "2025-01-01T00:05:00.000Z"
  }
}
```

**What to do after:**
- Navigate to Home Screen

**Error Responses:**
- `404` - User not found (shouldn't happen)
- `500` - Server error

---

### 3. Get User Profile

**Endpoint:** `GET /auth/user/{user_id}`

**Description:** Get complete user information

**When to call:** When loading user profile, checking if user has name, etc.

**Success Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "firebase_uid": "abc123xyz",
    "phone_number": "+919876543210",
    "full_name": "Nik Kumar",
    "created_at": "2025-01-01T00:00:00.000Z",
    "last_login": "2025-01-01T00:05:00.000Z"
  }
}
```

**Error Responses:**
- `404` - User not found
- `500` - Server error

---

## React Native Integration Steps

### Step 1: Install Dependencies
```bash
npm install @react-native-firebase/app @react-native-firebase/auth
# or
yarn add @react-native-firebase/app @react-native-firebase/auth

# For iOS
cd ios && pod install && cd ..
```

### Step 2: Initialize Firebase

Add Firebase configuration to your app (use the config from Firebase Console).

### Step 3: Key Functions to Implement

You need to implement these core functions:

#### A. Send OTP
```javascript
// Function signature
sendOTP(phoneNumber) → returns confirmation object

// What it does:
// 1. Formats phone: "+91" + phoneNumber
// 2. Calls Firebase: auth().signInWithPhoneNumber(formattedPhone)
// 3. Firebase sends SMS with OTP
// 4. Returns confirmation object (needed for verification)
```

#### B. Verify OTP
```javascript
// Function signature
verifyOTP(confirmation, otpCode) → returns { user_id, is_new_user }

// What it does:
// 1. Calls Firebase: confirmation.confirm(otpCode)
// 2. If OTP correct: Firebase returns user with ID token
// 3. Gets ID token: user.getIdToken()
// 4. Calls backend: POST /auth/verify-otp with id_token
// 5. Backend returns: { user_id, phone_number, is_new_user }
// 6. Store user_id in AsyncStorage
// 7. Return result
```

#### C. Update Profile
```javascript
// Function signature
updateProfile(userId, fullName) → returns updated user data

// What it does:
// 1. Calls backend: PUT /auth/user/{userId}/profile
// 2. Sends: { "full_name": fullName }
// 3. Returns success/error
```

#### D. Logout
```javascript
// Function signature
logout() → clears user session

// What it does:
// 1. Firebase: auth().signOut()
// 2. Remove user_id from AsyncStorage
// 3. Navigate to Login screen
```

### Step 4: Screens to Create

#### Screen 1: Phone Input Screen
- Input field for 10-digit phone number
- "Send OTP" button
- Loading state while sending
- Error handling

#### Screen 2: OTP Verification Screen
- Display phone number
- Input field for 6-digit OTP
- "Verify" button
- "Resend OTP" button
- Loading state
- Error handling (wrong OTP, expired OTP)

#### Screen 3: Name Input Screen (only for new users)
- Input field for full name
- "Continue" button
- Loading state

### Step 5: Navigation Logic
```
App Start
  ↓
Check AsyncStorage for user_id
  ↓
├─ If user_id exists → Home Screen
└─ If no user_id → Phone Input Screen
     ↓
  OTP Verification Screen
     ↓
  Check is_new_user
     ↓
  ├─ true → Name Input Screen → Home Screen
  └─ false → Home Screen
```

---

## Error Handling

### Firebase Errors (Client-side)

| Error Code | Meaning | User Message | Action |
|------------|---------|--------------|--------|
| `auth/invalid-phone-number` | Wrong phone format | "Invalid phone number" | Show error, allow retry |
| `auth/invalid-verification-code` | Wrong OTP entered | "Wrong OTP. Try again." | Show error, allow retry |
| `auth/code-expired` | OTP expired (10 min) | "OTP expired. Request new one." | Show resend button |
| `auth/too-many-requests` | Rate limit hit | "Too many attempts. Try later." | Disable send button temporarily |
| `auth/network-request-failed` | No internet | "Check your connection" | Show retry button |

### Backend Errors

| Status Code | Meaning | User Message | Action |
|-------------|---------|--------------|--------|
| `400` | Bad request | "Something went wrong" | Log error, contact support |
| `401` | Invalid token | "Session expired. Login again." | Navigate to Login screen |
| `404` | User not found | "User not found" | Contact support |
| `500` | Server error | "Server error. Try again." | Show retry button |

### Example Error Handling
```javascript
try {
  const result = await verifyOTP(confirmation, otp);
  // Handle success
} catch (error) {
  if (error.code === 'auth/invalid-verification-code') {
    showError('Wrong OTP. Please try again.');
  } else if (error.code === 'auth/code-expired') {
    showError('OTP expired. Request a new one.');
  } else {
    showError('Something went wrong. Please try again.');
  }
}
```

---

## Testing

### Test Phone Numbers (Configured in Firebase)

Use these for testing without SMS charges:
```
Phone: +919876543210  →  OTP: 123456
Phone: +919999999999  →  OTP: 654321
```

These numbers:
- Don't send real SMS
- Always accept the configured OTP
- Can be used unlimited times
- Perfect for development/testing

### Test Scenarios

#### 1. New User Flow
```
1. Enter phone: 9876543210
2. Click "Send OTP"
3. Enter OTP: 123456
4. Backend returns: is_new_user = true
5. Show Name Input screen
6. Enter name: "Test User"
7. Navigate to Home
```

#### 2. Existing User Flow
```
1. Enter phone: 9876543210 (same as above)
2. Click "Send OTP"
3. Enter OTP: 123456
4. Backend returns: is_new_user = false (same user_id)
5. Navigate directly to Home
```

#### 3. Wrong OTP
```
1. Enter phone: 9876543210
2. Enter wrong OTP: 999999
3. Firebase error: "Invalid verification code"
4. Show error message
5. Allow retry (don't navigate away)
```

#### 4. Resend OTP
```
1. Enter phone: 9876543210
2. Wait on OTP screen
3. Click "Resend OTP"
4. New OTP sent
5. Old OTP becomes invalid
6. Enter new OTP
```

#### 5. OTP Expiry
```
1. Enter phone: 9876543210
2. Wait 11 minutes (OTP expires after 10 min)
3. Enter OTP
4. Firebase error: "Code expired"
5. Show "Request new OTP" message
```

### Testing Checklist

- [ ] Send OTP with test phone number
- [ ] Verify OTP with correct code
- [ ] Verify OTP with wrong code
- [ ] Resend OTP functionality
- [ ] OTP expiry handling
- [ ] New user flow (enters name)
- [ ] Existing user flow (skips name)
- [ ] Network error handling
- [ ] Backend API errors (401, 500)
- [ ] Logout functionality
- [ ] App restart with saved user_id

---

## Important Notes

### Phone Number Format

Always send phone numbers to Firebase with country code:
```javascript
// ❌ Wrong
const phone = "9876543210";

// ✅ Correct
const phone = "+919876543210";
```

### Token Expiration

Firebase ID tokens expire after 1 hour. If you get 401 error from backend, user needs to login again.

### Storage

Store only `user_id` locally (in AsyncStorage). Don't store:
- Firebase ID token (it expires)
- OTP code
- Phone number (optional, for UX only)

### Security

- Never log OTP codes in production
- Never log Firebase ID tokens
- Handle all errors gracefully
- Use HTTPS in production

### Rate Limits

Firebase automatically limits:
- 5 OTP attempts per phone per hour
- 10 OTP requests per phone per day

Handle `auth/too-many-requests` error appropriately.

---

## Integration Checklist

Before starting implementation:
- [ ] Firebase project created
- [ ] Phone authentication enabled in Firebase Console
- [ ] Android app registered (google-services.json downloaded)
- [ ] iOS app registered (GoogleService-Info.plist downloaded)
- [ ] Test phone numbers configured in Firebase
- [ ] Backend API running and tested

During implementation:
- [ ] Install Firebase packages
- [ ] Initialize Firebase in app
- [ ] Implement sendOTP function
- [ ] Implement verifyOTP function
- [ ] Implement updateProfile function
- [ ] Create Phone Input screen
- [ ] Create OTP Verification screen
- [ ] Create Name Input screen
- [ ] Set up navigation
- [ ] Add error handling
- [ ] Test all flows

---

## API Documentation

Full API documentation available at:
- **Swagger UI:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/auth/health

---

## Support

### Common Issues

**Issue:** "OTP not received"
- Check phone number format (+91XXXXXXXXXX)
- Try test phone numbers first
- Check Firebase Console → Usage

**Issue:** "Invalid token" error from backend
- Token might be expired (>1 hour)
- Verify Firebase project matches backend
- Check backend logs

**Issue:** Firebase initialization error
- Verify google-services.json placement (Android)
- Verify GoogleService-Info.plist placement (iOS)
- Clean and rebuild app

### Contact

Backend issues: Check server logs at `http://localhost:8000`
Firebase issues: Check Firebase Console → Authentication → Usage

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-01  
**Backend API Version:** 1.0.0

---

## Quick Reference

### API Endpoints Summary
```
POST   /auth/verify-otp              - Verify OTP and get user_id
PUT    /auth/user/{user_id}/profile  - Update user name
GET    /auth/user/{user_id}          - Get user profile
```

### Firebase Methods Summary
```javascript
auth().signInWithPhoneNumber(phone)  - Send OTP
confirmation.confirm(otp)             - Verify OTP
user.getIdToken()                     - Get ID token for backend
auth().signOut()                      - Logout
```

### Key Data Flow
```
Phone Number → Firebase → OTP → User enters OTP → Firebase Token → Backend → user_id → AsyncStorage
```

---