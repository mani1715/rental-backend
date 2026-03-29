"""
Test authentication flow
"""
import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

JWT_SECRET = "rentease_secret_key"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        print(f"✅ Token valid")
        print(f"   User ID: {user_id}")
        print(f"   Expires: {datetime.fromtimestamp(payload.get('exp'))}")
        return payload
    except JWTError as e:
        print(f"❌ Token invalid: {e}")
        return None

print("="*60)
print("Testing JWT Token Creation and Validation")
print("="*60)

# Test token creation
test_user_id = "507f1f77bcf86cd799439011"
print(f"\n1. Creating token for user: {test_user_id}")
token = create_token(test_user_id)
print(f"   Token: {token[:50]}...")

# Test token verification
print(f"\n2. Verifying token...")
payload = verify_token(token)

# Test invalid token
print(f"\n3. Testing invalid token...")
invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.token"
verify_token(invalid_token)

# Test expired token (manually create one)
print(f"\n4. Testing expired token...")
expired_payload = {
    "user_id": test_user_id,
    "exp": datetime.now(timezone.utc) - timedelta(days=1)  # Expired yesterday
}
expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
verify_token(expired_token)

print("\n" + "="*60)
print("Authentication tests completed!")
print("="*60)

print("\n📝 Frontend should send token in header:")
print("   Authorization: Bearer " + token[:30] + "...")
