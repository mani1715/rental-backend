"""
RentEase - Rental Marketplace API
FastAPI Backend with MongoDB
"""

import os
import uuid
import bcrypt
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from jose import JWTError, jwt
from dotenv import load_dotenv
from bson import ObjectId
import google.generativeai as genai

load_dotenv()

# Configuration
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "rentease_db")
JWT_SECRET = os.environ.get("JWT_SECRET", "rentease_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Configure Gemini AI if API key is available
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"[GEMINI] API configured successfully")
else:
    print(f"[GEMINI] Warning: GEMINI_API_KEY not set")

# Security
security = HTTPBearer()

# Database client
client: AsyncIOMotorClient = None
db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    print(f"Connected to MongoDB: {MONGO_URL}/{DB_NAME}")
    yield
    client.close()
    print("MongoDB connection closed")


app = FastAPI(
    title="RentEase API",
    description="Rental Marketplace API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - Allow frontend URL from environment
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "https://rental-frontend-production-1987.up.railway.app",
        "https://rental-frontend-production.up.railway.app",
        "https://your-frontend-domain.vercel.app",
        frontend_url,
        "*"  # Allow all origins for development - remove in production if needed
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Create uploads directory and mount it for static file serving
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="api_uploads")


# Helper Functions
def hash_password(password: str) -> str:
    """
    Hash password using bcrypt directly - COMPLETELY FOOLPROOF
    This bypasses passlib to avoid any configuration issues
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
    try:
        # Validate input
        if not plain_password or not isinstance(plain_password, str):
            print(f"[VERIFY] ❌ Invalid password input: {type(plain_password)}")
            return False
        
        if not hashed_password or not isinstance(hashed_password, str):
            print(f"[VERIFY] ❌ Invalid hash input: {type(hashed_password)}")
            return False
        
        # Clean the password
        clean_password = plain_password.strip()
        
        # Truncate to 50 characters (must match hash_password)
        safe_password = clean_password[:50]
        
        print(f"[VERIFY] Password length: {len(clean_password)} → {len(safe_password)}")
        print(f"[VERIFY] Hash format: {hashed_password[:7] if len(hashed_password) >= 7 else hashed_password}")
        
        # Convert to bytes
        password_bytes = safe_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        
        # Verify
        result = bcrypt.checkpw(password_bytes, hashed_bytes)
        print(f"[VERIFY] Result: {result}")
        
        return result
        
    except Exception as e:
        print(f"[VERIFY] ❌ Error during verification: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format"""
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            result["id"] = str(value)
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Authentication middleware - extracts and validates JWT token
    """
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        print(f"[AUTH] Token received: {token[:20]}...")
        
        # Decode and verify JWT token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        
        print(f"[AUTH] Decoded user_id: {user_id}")
        
        if not user_id:
            print(f"[AUTH] ❌ No user_id in token payload")
            raise HTTPException(
                status_code=401, 
                detail="Invalid token: missing user_id"
            )
        
        # Find user in database
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            print(f"[AUTH] ❌ User not found in database: {user_id}")
            raise HTTPException(
                status_code=401, 
                detail="User not found"
            )
        
        # Serialize and return user data
        user_data = serialize_doc(user)
        print(f"[AUTH] ✅ User authenticated: {user_data.get('email')}")
        
        return user_data
        
    except JWTError as e:
        print(f"[AUTH] ❌ JWT Error: {str(e)}")
        raise HTTPException(
            status_code=401, 
            detail=f"Invalid or expired token: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH] ❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=401, 
            detail="Authentication failed"
        )


# Pydantic Models
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)  # Removed max_length - we'll handle it in code


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SelectRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(OWNER|CUSTOMER)$")


class ListingCreate(BaseModel):
    title: str
    type: str
    price: float
    squareFeet: Optional[float] = None
    facilities: List[str] = []
    addressText: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    googleMapsLink: Optional[str] = None
    description: Optional[str] = ""
    bedrooms: Optional[int] = 1
    bathrooms: Optional[int] = 1
    images: List[str] = []
    status: str = "available"


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None


class ConversationCreate(BaseModel):
    listingId: str
    ownerId: str


class MessageCreate(BaseModel):
    text: str


class BookingCreate(BaseModel):
    name: Optional[str] = ""
    phone: Optional[str] = ""
    message: Optional[str] = ""


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|approved|rejected|cancelled)$")


class AIDescriptionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    propertyType: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    squareFeet: Optional[float] = None


# ==================== API ROUTES ====================

# Health Check
@app.get("/")
async def root():
    return {"status": "ok", "message": "RentEase API is running"}

@app.get("/api")
async def health_check():
    return {"status": "ok", "message": "RentEase API is running"}


# ==================== AUTH ROUTES ====================

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new user"""
    try:
        # Debug logging
        print(f"[REGISTER] Received request for: {req.email}")
        print(f"[REGISTER] Password received, length: {len(req.password)}")
        
        # Check if user already exists
        existing_user = await db.users.find_one({"email": req.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash the password - this is now foolproof and cannot fail
        print(f"[REGISTER] Hashing password...")
        hashed_password = hash_password(req.password)
        print(f"[REGISTER] Password hashed successfully")
        
        # Create new user
        user_doc = {
            "_id": ObjectId(),
            "name": req.name,
            "email": req.email,
            "password": hashed_password,
            "role": None,  # Role will be selected later
            "createdAt": datetime.now(timezone.utc)
        }
        
        result = await db.users.insert_one(user_doc)
        print(f"[REGISTER] User created with ID: {result.inserted_id}")
        
        # Create token
        token = create_token(str(user_doc["_id"]))
        
        # Return user data without password
        user_data = serialize_doc(user_doc)
        user_data.pop("password", None)
        
        return {
            "success": True,
            "token": token,
            "user": user_data,
            "requiresRoleSelection": True
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REGISTER ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login user"""
    try:
        print(f"[LOGIN] ═══════════════════════════════════════════")
        print(f"[LOGIN] Email: {req.email}")
        print(f"[LOGIN] Password length: {len(req.password)}")
        
        # Find user
        user = await db.users.find_one({"email": req.email})
        
        if not user:
            print(f"[LOGIN] ❌ User not found in database")
            raise HTTPException(
                status_code=401, 
                detail="Invalid email or password"
            )
        
        print(f"[LOGIN] ✅ User found: {user.get('email')}")
        print(f"[LOGIN] User ID: {user.get('_id')}")
        print(f"[LOGIN] User has password: {bool(user.get('password'))}")
        print(f"[LOGIN] Stored password hash length: {len(user.get('password', ''))}")
        
        # Verify password
        print(f"[LOGIN] Verifying password...")
        password_match = verify_password(req.password, user["password"])
        print(f"[LOGIN] Password match: {password_match}")
        
        if not password_match:
            print(f"[LOGIN] ❌ Password verification failed")
            # Let's also try to debug this
            print(f"[LOGIN] Input password (first 3 chars): {req.password[:3]}...")
            print(f"[LOGIN] Hash (first 20 chars): {user['password'][:20]}...")
            raise HTTPException(
                status_code=401, 
                detail="Invalid email or password"
            )
        
        print(f"[LOGIN] ✅ Password verified successfully")
        
        # Create token
        token = create_token(str(user["_id"]))
        print(f"[LOGIN] Token created")
        
        # Return user data without password
        user_data = serialize_doc(user)
        user_data.pop("password", None)
        
        print(f"[LOGIN] ✅ Login successful for: {user_data.get('email')}")
        
        return {
            "success": True,
            "token": token,
            "user": user_data,
            "requiresRoleSelection": user_data.get("role") is None
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOGIN] ❌ Unexpected error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Login failed: {str(e)}"
        )


@app.post("/api/auth/test-login")
async def test_login_credentials(req: LoginRequest):
    """
    Test endpoint to debug login issues
    Returns detailed info about why login might fail
    """
    try:
        print(f"[TEST-LOGIN] Testing credentials for: {req.email}")
        
        # Find user
        user = await db.users.find_one({"email": req.email})
        
        response = {
            "email": req.email,
            "userExists": user is not None,
        }
        
        if not user:
            response["issue"] = "User not found in database"
            response["suggestion"] = "Check if user registered with this email"
            return response
        
        # User exists - check password hash
        response["userId"] = str(user["_id"])
        response["hasPassword"] = bool(user.get("password"))
        response["passwordHashLength"] = len(user.get("password", ""))
        response["hashPrefix"] = user.get("password", "")[:7]
        
        # Try to verify password
        try:
            password_match = verify_password(req.password, user["password"])
            response["passwordMatches"] = password_match
            
            if not password_match:
                response["issue"] = "Password does not match stored hash"
                response["suggestion"] = "User may have registered with a different password, or password hashing changed"
        except Exception as e:
            response["passwordMatches"] = False
            response["verificationError"] = str(e)
            response["issue"] = "Error during password verification"
        
        return response
        
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

        user_data.pop("password", None)
        
        print(f"[LOGIN] ✅ Login successful for: {user_data.get('email')}")
        
        return {
            "success": True,
            "token": token,
            "user": user_data,
            "requiresRoleSelection": user_data.get("role") is None
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOGIN] ❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Login failed: {str(e)}"
        )


# ==================== USER ROUTES ====================

@app.get("/api/user/me")
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "success": True,
        "user": current_user
    }


@app.post("/api/user/select-role")
async def select_role(req: SelectRoleRequest, current_user: dict = Depends(get_current_user)):
    """Select user role (OWNER or CUSTOMER)"""
    # Update user role
    result = await db.users.update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {"role": req.role}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update role")
    
    # Get updated user
    updated_user = await db.users.find_one({"_id": ObjectId(current_user["id"])})
    user_data = serialize_doc(updated_user)
    user_data.pop("password", None)
    
    return {
        "success": True,
        "user": user_data
    }


# ==================== LISTINGS ROUTES ====================

@app.get("/api/listings")
async def get_listings(
    ownerId: Optional[str] = None,
    type: Optional[str] = None,
    location: Optional[str] = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    status: Optional[str] = None
):
    """Get all listings with optional filters"""
    query = {}
    
    if ownerId:
        query["ownerId"] = ownerId
    if type:
        query["type"] = type
    if location:
        query["addressText"] = {"$regex": location, "$options": "i"}
    if minPrice is not None or maxPrice is not None:
        query["price"] = {}
        if minPrice is not None:
            query["price"]["$gte"] = minPrice
        if maxPrice is not None:
            query["price"]["$lte"] = maxPrice
    if bedrooms:
        query["bedrooms"] = bedrooms
    if bathrooms:
        query["bathrooms"] = bathrooms
    if status:
        query["status"] = status
    
    listings = await db.listings.find(query).to_list(length=100)
    
    return {
        "success": True,
        "listings": [serialize_doc(listing) for listing in listings]
    }


@app.get("/api/listings/{listing_id}")
async def get_listing(listing_id: str):
    """Get a single listing by ID"""
    try:
        listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        return {
            "success": True,
            "listing": serialize_doc(listing)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/listings")
async def create_listing(listing: ListingCreate, current_user: dict = Depends(get_current_user)):
    """Create a new listing (OWNER only)"""
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can create listings")
    
    listing_doc = {
        "_id": ObjectId(),
        **listing.dict(),
        "ownerId": current_user["id"],
        "createdAt": datetime.now(timezone.utc),
        "rating": 0,
        "reviewCount": 0
    }
    
    await db.listings.insert_one(listing_doc)
    
    return {
        "success": True,
        "listing": serialize_doc(listing_doc)
    }


@app.put("/api/listings/{listing_id}")
async def update_listing(
    listing_id: str,
    listing: ListingCreate,
    current_user: dict = Depends(get_current_user)
):
    """Update a listing (OWNER only, own listings only)"""
    try:
        # Check if listing exists and belongs to current user
        existing_listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
        if not existing_listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        if existing_listing.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You can only update your own listings")
        
        # Update listing
        result = await db.listings.update_one(
            {"_id": ObjectId(listing_id)},
            {"$set": listing.dict()}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Failed to update listing")
        
        # Get updated listing
        updated_listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
        
        return {
            "success": True,
            "listing": serialize_doc(updated_listing)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/listings/{listing_id}")
async def delete_listing(listing_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a listing (OWNER only, own listings only)"""
    try:
        # Check if listing exists and belongs to current user
        existing_listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
        if not existing_listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        if existing_listing.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own listings")
        
        # Delete listing
        await db.listings.delete_one({"_id": ObjectId(listing_id)})
        
        return {
            "success": True,
            "message": "Listing deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== UPLOAD ROUTE ====================

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload a file (images for listings)"""
    try:
        print(f"[UPLOAD] ═══════════════════════════════════════════")
        print(f"[UPLOAD] User: {current_user.get('email')}")
        print(f"[UPLOAD] Filename: {file.filename}")
        print(f"[UPLOAD] Content Type: {file.content_type}")
        
        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Check file size (max 5MB)
        content = await file.read()
        file_size = len(content)
        max_size = 5 * 1024 * 1024  # 5MB
        
        print(f"[UPLOAD] File size: {file_size / 1024:.2f} KB")
        
        if file_size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {max_size / 1024 / 1024}MB"
            )
        
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join("uploads", unique_filename)
        
        print(f"[UPLOAD] Saving to: {file_path}")
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Verify file was saved
        if not os.path.exists(file_path):
            raise Exception("File was not saved properly")
        
        saved_size = os.path.getsize(file_path)
        print(f"[UPLOAD] ✅ File saved successfully ({saved_size / 1024:.2f} KB)")
        
        # Return file URL (relative path that works with static serving)
        file_url = f"/uploads/{unique_filename}"
        
        # Also return full URL for frontend convenience
        backend_url = os.environ.get("BACKEND_URL", "https://rental-backend-production-3c03.up.railway.app")
        full_url = f"{backend_url}/uploads/{unique_filename}"
        
        print(f"[UPLOAD] Relative URL: {file_url}")
        print(f"[UPLOAD] Full URL: {full_url}")
        
        return {
            "success": True,
            "url": file_url,
            "fullUrl": full_url,
            "image": file_url,
            "imageUrl": full_url,
            "filename": unique_filename,
            "size": file_size
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[UPLOAD] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


# ==================== WISHLIST ROUTES ====================



@app.get("/api/test-image")
async def test_image():
    """Test endpoint to check image serving"""
    try:
        # List all files in uploads directory
        upload_dir = "uploads"
        if not os.path.exists(upload_dir):
            return {
                "success": False,
                "message": "Uploads directory does not exist",
                "directory": upload_dir
            }
        
        files = os.listdir(upload_dir)
        image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
        
        return {
            "success": True,
            "uploadsDirectory": upload_dir,
            "directoryExists": True,
            "totalFiles": len(files),
            "imageFiles": len(image_files),
            "sampleImages": image_files[:5] if image_files else [],
            "sampleUrls": [f"/uploads/{f}" for f in image_files[:5]] if image_files else []
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/wishlist")
async def get_wishlist(current_user: dict = Depends(get_current_user)):
    """Get user's wishlist"""
    wishlist_items = await db.wishlist.find({"userId": current_user["id"]}).to_list(length=100)
    
    # Get listing details for each wishlist item
    listing_ids = [ObjectId(item["listingId"]) for item in wishlist_items]
    listings = await db.listings.find({"_id": {"$in": listing_ids}}).to_list(length=100)
    
    return {
        "success": True,
        "wishlist": [serialize_doc(listing) for listing in listings]
    }


@app.post("/api/wishlist")
async def add_to_wishlist(data: dict, current_user: dict = Depends(get_current_user)):
    """Add listing to wishlist"""
    listing_id = data.get("listingId")
    if not listing_id:
        raise HTTPException(status_code=400, detail="listingId is required")
    
    # Check if already in wishlist
    existing = await db.wishlist.find_one({
        "userId": current_user["id"],
        "listingId": listing_id
    })
    
    if existing:
        return {
            "success": True,
            "message": "Already in wishlist"
        }
    
    # Add to wishlist
    wishlist_item = {
        "_id": ObjectId(),
        "userId": current_user["id"],
        "listingId": listing_id,
        "createdAt": datetime.now(timezone.utc)
    }
    
    await db.wishlist.insert_one(wishlist_item)
    
    return {
        "success": True,
        "message": "Added to wishlist"
    }


@app.delete("/api/wishlist/{listing_id}")
async def remove_from_wishlist(listing_id: str, current_user: dict = Depends(get_current_user)):
    """Remove listing from wishlist"""
    result = await db.wishlist.delete_one({
        "userId": current_user["id"],
        "listingId": listing_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found in wishlist")
    
    return {
        "success": True,
        "message": "Removed from wishlist"
    }


# ==================== REVIEWS ROUTES ====================

@app.get("/api/reviews/{listing_id}")
async def get_reviews(listing_id: str):
    """Get all reviews for a listing"""
    reviews = await db.reviews.find({"listingId": listing_id}).to_list(length=100)
    
    return {
        "success": True,
        "reviews": [serialize_doc(review) for review in reviews]
    }


@app.post("/api/reviews/{listing_id}")
async def create_review(listing_id: str, review: ReviewCreate, current_user: dict = Depends(get_current_user)):
    """Create a review for a listing"""
    # Check if listing exists
    listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # Check if user already reviewed this listing
    existing_review = await db.reviews.find_one({
        "listingId": listing_id,
        "userId": current_user["id"]
    })
    
    if existing_review:
        raise HTTPException(status_code=400, detail="You have already reviewed this listing")
    
    # Create review
    review_doc = {
        "_id": ObjectId(),
        "listingId": listing_id,
        "userId": current_user["id"],
        "userName": current_user.get("name", "Anonymous"),
        "rating": review.rating,
        "comment": review.comment,
        "createdAt": datetime.now(timezone.utc)
    }
    
    await db.reviews.insert_one(review_doc)
    
    # Update listing rating - optimized query with projection
    all_reviews = await db.reviews.find({"listingId": listing_id}, {"rating": 1}).to_list(length=1000)
    avg_rating = sum(r["rating"] for r in all_reviews) / len(all_reviews)
    
    await db.listings.update_one(
        {"_id": ObjectId(listing_id)},
        {"$set": {"rating": avg_rating, "reviewCount": len(all_reviews)}}
    )
    
    return {
        "success": True,
        "review": serialize_doc(review_doc)
    }


@app.put("/api/reviews/{review_id}")
async def update_review(review_id: str, review: ReviewUpdate, current_user: dict = Depends(get_current_user)):
    """Update a review"""
    try:
        # Check if review exists and belongs to current user
        existing_review = await db.reviews.find_one({"_id": ObjectId(review_id)})
        if not existing_review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        if existing_review.get("userId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You can only update your own reviews")
        
        # Update review
        update_data = {k: v for k, v in review.dict().items() if v is not None}
        result = await db.reviews.update_one(
            {"_id": ObjectId(review_id)},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Failed to update review")
        
        # Recalculate listing rating - optimized query with projection
        listing_id = existing_review["listingId"]
        all_reviews = await db.reviews.find({"listingId": listing_id}, {"rating": 1}).to_list(length=1000)
        avg_rating = sum(r["rating"] for r in all_reviews) / len(all_reviews)
        
        await db.listings.update_one(
            {"_id": ObjectId(listing_id)},
            {"$set": {"rating": avg_rating}}
        )
        
        # Get updated review
        updated_review = await db.reviews.find_one({"_id": ObjectId(review_id)})
        
        return {
            "success": True,
            "review": serialize_doc(updated_review)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/reviews/{review_id}")
async def delete_review(review_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a review"""
    try:
        # Check if review exists and belongs to current user
        existing_review = await db.reviews.find_one({"_id": ObjectId(review_id)})
        if not existing_review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        if existing_review.get("userId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own reviews")
        
        listing_id = existing_review["listingId"]
        
        # Delete review
        await db.reviews.delete_one({"_id": ObjectId(review_id)})
        
        # Recalculate listing rating - optimized query with projection
        all_reviews = await db.reviews.find({"listingId": listing_id}, {"rating": 1}).to_list(length=1000)
        if all_reviews:
            avg_rating = sum(r["rating"] for r in all_reviews) / len(all_reviews)
            review_count = len(all_reviews)
        else:
            avg_rating = 0
            review_count = 0
        
        await db.listings.update_one(
            {"_id": ObjectId(listing_id)},
            {"$set": {"rating": avg_rating, "reviewCount": review_count}}
        )
        
        return {
            "success": True,
            "message": "Review deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== CONVERSATIONS/CHAT ROUTES ====================

@app.post("/api/conversations")
async def create_conversation(conv: ConversationCreate, current_user: dict = Depends(get_current_user)):
    """Create a new conversation"""
    # Check if conversation already exists
    existing = await db.conversations.find_one({
        "listingId": conv.listingId,
        "customerId": current_user["id"]
    })
    
    if existing:
        return {
            "success": True,
            "conversation": serialize_doc(existing)
        }
    
    # Create new conversation
    conversation_doc = {
        "_id": ObjectId(),
        "listingId": conv.listingId,
        "customerId": current_user["id"],
        "ownerId": conv.ownerId,
        "createdAt": datetime.now(timezone.utc),
        "lastMessage": None,
        "lastMessageAt": None
    }
    
    await db.conversations.insert_one(conversation_doc)
    
    return {
        "success": True,
        "conversation": serialize_doc(conversation_doc)
    }


@app.get("/api/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """Get all conversations for current user"""
    if current_user.get("role") == "OWNER":
        query = {"ownerId": current_user["id"]}
    else:
        query = {"customerId": current_user["id"]}
    
    conversations = await db.conversations.find(query).to_list(length=100)
    
    return {
        "success": True,
        "conversations": [serialize_doc(conv) for conv in conversations]
    }


# ==================== MESSAGES ROUTES ====================

@app.get("/api/messages/{conversation_id}")
async def get_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Get all messages for a conversation"""
    try:
        # Verify user is part of the conversation
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if conversation.get("customerId") != current_user["id"] and conversation.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")
        
        # Get messages
        messages = await db.messages.find({"conversationId": conversation_id}).sort("createdAt", 1).to_list(length=1000)
        
        return {
            "success": True,
            "messages": [serialize_doc(msg) for msg in messages]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/messages/{conversation_id}")
async def send_message(conversation_id: str, message: MessageCreate, current_user: dict = Depends(get_current_user)):
    """Send a message in a conversation"""
    try:
        # Verify user is part of the conversation
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if conversation.get("customerId") != current_user["id"] and conversation.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")
        
        # Create message
        message_doc = {
            "_id": ObjectId(),
            "conversationId": conversation_id,
            "senderId": current_user["id"],
            "senderName": current_user.get("name", "Unknown"),
            "text": message.text,
            "createdAt": datetime.now(timezone.utc),
            "read": False
        }
        
        await db.messages.insert_one(message_doc)
        
        # Update conversation's last message
        await db.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {
                "$set": {
                    "lastMessage": message.text,
                    "lastMessageAt": datetime.now(timezone.utc)
                }
            }
        )
        
        return {
            "success": True,
            "message": serialize_doc(message_doc)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/conversations/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Mark all messages in a conversation as read"""
    try:
        # Verify user is part of the conversation
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if conversation.get("customerId") != current_user["id"] and conversation.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")
        
        # Mark all messages as read where current user is not the sender
        await db.messages.update_many(
            {
                "conversationId": conversation_id,
                "senderId": {"$ne": current_user["id"]}
            },
            {"$set": {"read": True}}
        )
        
        return {
            "success": True,
            "message": "Messages marked as read"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== BOOKING ROUTES ====================

@app.post("/api/bookings/{listing_id}")
async def create_booking(listing_id: str, booking: BookingCreate, current_user: dict = Depends(get_current_user)):
    """Create a booking request for a listing"""
    try:
        # Verify listing exists
        listing = await db.listings.find_one({"_id": ObjectId(listing_id)})
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Create booking
        booking_doc = {
            "_id": ObjectId(),
            "listingId": listing_id,
            "customerId": current_user["id"],
            "customerName": booking.name or current_user.get("name", "Unknown"),
            "customerEmail": current_user.get("email", ""),
            "customerPhone": booking.phone or "",
            "ownerId": listing.get("ownerId"),
            "propertyTitle": listing.get("title", ""),
            "message": booking.message,
            "status": "pending",
            "createdAt": datetime.now(timezone.utc)
        }
        
        await db.bookings.insert_one(booking_doc)
        
        return {
            "success": True,
            "booking": serialize_doc(booking_doc),
            "message": "Booking request sent successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/bookings/customer")
async def get_customer_bookings(current_user: dict = Depends(get_current_user)):
    """Get all bookings made by the current customer"""
    bookings = await db.bookings.find({"customerId": current_user["id"]}).sort("createdAt", -1).to_list(length=100)
    
    return {
        "success": True,
        "bookings": [serialize_doc(booking) for booking in bookings]
    }


@app.get("/api/bookings/owner")
async def get_owner_bookings(current_user: dict = Depends(get_current_user)):
    """Get all bookings for the current owner's listings"""
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can access this endpoint")
    
    bookings = await db.bookings.find({"ownerId": current_user["id"]}).sort("createdAt", -1).to_list(length=100)
    
    return {
        "success": True,
        "bookings": [serialize_doc(booking) for booking in bookings]
    }


@app.put("/api/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status_update: BookingStatusUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update booking status (owner only)"""
    try:
        # Verify booking exists
        booking = await db.bookings.find_one({"_id": ObjectId(booking_id)})
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Verify user is the owner
        if booking.get("ownerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Only the property owner can update booking status")
        
        # Update status
        await db.bookings.update_one(
            {"_id": ObjectId(booking_id)},
            {"$set": {"status": status_update.status, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        # Get updated booking
        updated_booking = await db.bookings.find_one({"_id": ObjectId(booking_id)})
        
        return {
            "success": True,
            "booking": serialize_doc(updated_booking)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/bookings/{booking_id}")
async def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    """Cancel a booking (customer only, for their own bookings)"""
    try:
        # Verify booking exists
        booking = await db.bookings.find_one({"_id": ObjectId(booking_id)})
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Verify user is the customer who made the booking
        if booking.get("customerId") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You can only cancel your own bookings")
        
        # Delete booking
        await db.bookings.delete_one({"_id": ObjectId(booking_id)})
        
        return {
            "success": True,
            "message": "Booking cancelled successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== OWNER PROFILE ROUTES ====================

@app.get("/api/owner/profile")
async def get_owner_profile(current_user: dict = Depends(get_current_user)):
    """Get owner profile"""
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can access this endpoint")
    
    # Get owner profile or create default
    profile = await db.owner_profiles.find_one({"userId": current_user["id"]})
    
    if not profile:
        # Create default profile
        profile = {
            "_id": ObjectId(),
            "userId": current_user["id"],
            "bio": "",
            "phone": "",
            "website": "",
            "createdAt": datetime.now(timezone.utc)
        }
        await db.owner_profiles.insert_one(profile)
    
    return {
        "success": True,
        "profile": serialize_doc(profile)
    }


@app.post("/api/owner/profile")
async def update_owner_profile(data: dict, current_user: dict = Depends(get_current_user)):
    """Update owner profile"""
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can access this endpoint")
    
    # Update or create profile
    result = await db.owner_profiles.update_one(
        {"userId": current_user["id"]},
        {"$set": data},
        upsert=True
    )
    
    profile = await db.owner_profiles.find_one({"userId": current_user["id"]})
    
    return {
        "success": True,
        "profile": serialize_doc(profile)
    }


# ==================== AI ROUTES ====================

@app.post("/api/ai/generate-description")
async def generate_description(req: AIDescriptionRequest):
    """
    Generate AI-powered property description using Gemini
    Returns fallback description if AI service is unavailable
    """
    try:
        print(f"[AI] ═══════════════════════════════════════════")
        print(f"[AI] Generating description for: {req.title}")
        print(f"[AI] API Key configured: {bool(GEMINI_API_KEY)}")
        
        # If no API key, return a professionally crafted fallback
        if not GEMINI_API_KEY:
            print(f"[AI] ⚠️  No API key - using fallback description")
            fallback = generate_fallback_description(req)
            return {
                "success": True,
                "description": fallback,
                "aiGenerated": False,
                "message": "Using template description (Gemini API key not configured)"
            }
        
        # Prepare the prompt
        property_details = []
        property_details.append(f"Title: {req.title}")
        property_details.append(f"Location: {req.location}")
        property_details.append(f"Price: ${req.price:,.2f}")
        
        if req.propertyType:
            property_details.append(f"Type: {req.propertyType}")
        if req.bedrooms:
            property_details.append(f"Bedrooms: {req.bedrooms}")
        if req.bathrooms:
            property_details.append(f"Bathrooms: {req.bathrooms}")
        if req.squareFeet:
            property_details.append(f"Size: {req.squareFeet} sq ft")
        
        prompt = f"""Generate a professional, engaging property description for a rental listing with the following details:

{chr(10).join(property_details)}

Requirements:
- Write 2-3 paragraphs (150-200 words)
- Highlight key features and benefits
- Use professional but friendly tone
- Emphasize location advantages
- Make it appealing to potential renters
- Do not use markdown formatting
- Do not include pricing or contact information

Generate only the description text, no other commentary."""

        print(f"[AI] Prompt prepared ({len(prompt)} chars)")
        print(f"[AI] Calling Gemini API...")
        
        try:
            # Generate description using Gemini
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'top_k': 40,
                    'max_output_tokens': 500,
                }
            )
            
            if not response or not response.text:
                raise Exception("Empty response from Gemini API")
            
            description = response.text.strip()
            
            print(f"[AI] ✅ AI description generated ({len(description)} chars)")
            
            return {
                "success": True,
                "description": description,
                "aiGenerated": True
            }
            
        except Exception as gemini_error:
            print(f"[AI] ⚠️  Gemini API error: {str(gemini_error)}")
            print(f"[AI] Falling back to template description")
            
            # Return fallback instead of failing
            fallback = generate_fallback_description(req)
            return {
                "success": True,
                "description": fallback,
                "aiGenerated": False,
                "message": f"Gemini API unavailable: {str(gemini_error)[:100]}"
            }
        
    except Exception as e:
        print(f"[AI] ❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Still return fallback instead of error
        try:
            fallback = generate_fallback_description(req)
            return {
                "success": True,
                "description": fallback,
                "aiGenerated": False,
                "message": f"Error occurred, using template: {str(e)[:100]}"
            }
        except:
            # Last resort - return basic description
            return {
                "success": True,
                "description": f"Welcome to this beautiful {req.propertyType or 'property'} located in {req.location}. This well-maintained property is available for ${req.price:,.2f} per month. Contact us today to schedule a viewing and make this your new home!",
                "aiGenerated": False,
                "message": "Using basic template"
            }


def generate_fallback_description(req: AIDescriptionRequest) -> str:
    """
    Generate a professional template-based description when AI is unavailable
    """
    property_type = req.propertyType or "property"
    bedrooms_text = f"{req.bedrooms}-bedroom " if req.bedrooms else ""
    bathrooms_text = f" with {req.bathrooms} bathroom{'s' if req.bathrooms != 1 else ''}" if req.bathrooms else ""
    size_text = f" spanning {req.squareFeet:,.0f} square feet" if req.squareFeet else ""
    
    # First paragraph - property introduction
    para1 = f"Welcome to this exceptional {bedrooms_text}{property_type.lower()} located in the desirable area of {req.location}{bathrooms_text}{size_text}. "
    
    if req.bedrooms and req.bedrooms >= 2:
        para1 += "This spacious residence offers comfortable living spaces designed for modern lifestyles. "
    else:
        para1 += "This well-appointed residence provides everything you need for comfortable living. "
    
    # Second paragraph - location and amenities
    para2 = f"Situated in {req.location}, residents enjoy convenient access to local amenities, shopping, dining, and entertainment options. The property features quality finishes throughout and is maintained to high standards. "
    
    # Third paragraph - call to action
    para3 = f"Available for ${req.price:,.2f} per month, this {property_type.lower()} represents an excellent opportunity for those seeking quality accommodation in a prime location. Contact us today to schedule a viewing and discover all this property has to offer!"
    
    return para1 + para2 + para3
