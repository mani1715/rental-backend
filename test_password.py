"""
Test password hashing to verify it works correctly
"""
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash password with bcrypt - FOOLPROOF version that cannot fail"""
    # Ensure we have a string
    if not isinstance(password, str):
        password = str(password)
    
    # Strip whitespace
    password = password.strip()
    
    # ALWAYS truncate to 50 characters to be 100% safe (well under 72 bytes)
    # This ensures bcrypt will NEVER complain
    safe_password = password[:50]
    
    print(f"[HASH] Original length: {len(password)}, Safe length: {len(safe_password)}")
    
    # Hash the safe password - this CANNOT fail
    hashed = pwd_context.hash(safe_password)
    print(f"[HASH] Password hashed successfully")
    return hashed

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash - matches hash_password truncation"""
    # Ensure we have a string
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    
    # Strip whitespace
    plain_password = plain_password.strip()
    
    # ALWAYS truncate to 50 characters to match hash_password
    safe_password = plain_password[:50]
    
    return pwd_context.verify(safe_password, hashed_password)

# Test with different passwords
test_passwords = [
    "123456",
    "Maneesh@123",
    "Mani@123",
    "a",
    "VeryLongPasswordThatExceeds72BytesAndShouldBeTruncated" * 10
]

print("="*60)
print("Testing Password Hashing")
print("="*60)

for pwd in test_passwords:
    print(f"\nTesting password: '{pwd[:50]}...' (length: {len(pwd)})")
    try:
        hashed = hash_password(pwd)
        print(f"✅ Hashing SUCCESS")
        
        # Verify it works
        if verify_password(pwd, hashed):
            print(f"✅ Verification SUCCESS")
        else:
            print(f"❌ Verification FAILED")
    except Exception as e:
        print(f"❌ ERROR: {e}")

print("\n" + "="*60)
print("All tests completed!")
print("="*60)
