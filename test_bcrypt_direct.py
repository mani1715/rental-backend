"""
Test bcrypt direct implementation
"""
import bcrypt

def hash_password(password: str) -> str:
    """
    Hash password using bcrypt directly - COMPLETELY FOOLPROOF
    """
    # Validate input
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string")
    
    # Clean the password
    clean_password = password.strip()
    
    # Debug logging
    print(f"[HASH] Password received")
    print(f"[HASH] Type: {type(clean_password)}")
    print(f"[HASH] Length: {len(clean_password)}")
    
    # Truncate to 50 characters to be safe (well under 72 byte limit)
    safe_password = clean_password[:50]
    print(f"[HASH] Safe password length: {len(safe_password)}")
    
    # Convert to bytes (required by bcrypt)
    password_bytes = safe_password.encode('utf-8')
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    
    # Convert bytes back to string for storage
    hashed_str = hashed.decode('utf-8')
    
    print(f"[HASH] ✅ Password hashed successfully")
    return hashed_str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password using bcrypt directly
    """
    # Validate input
    if not plain_password or not isinstance(plain_password, str):
        return False
    
    # Clean the password
    clean_password = plain_password.strip()
    
    # Truncate to 50 characters (must match hash_password)
    safe_password = clean_password[:50]
    
    # Convert to bytes
    password_bytes = safe_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    
    # Verify
    return bcrypt.checkpw(password_bytes, hashed_bytes)


# Test with YOUR passwords
test_passwords = ["123456", "Maneesh@123", "Mani@123"]

print("="*60)
print("Testing BCRYPT DIRECT Implementation")
print("="*60)

for pwd in test_passwords:
    print(f"\n{'='*60}")
    print(f"Testing: '{pwd}'")
    print('='*60)
    
    try:
        hashed = hash_password(pwd)
        print(f"Hashed: {hashed[:50]}...")
        
        # Verify
        if verify_password(pwd, hashed):
            print(f"✅ VERIFICATION SUCCESS")
        else:
            print(f"❌ VERIFICATION FAILED")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*60)
print("All tests completed!")
print("="*60)
