"""
RentEase - Rental Marketplace API
FastAPI Backend with MongoDB
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

# Configuration
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "rentease_db")
JWT_SECRET = os.environ.get("JWT_SECRET", "rentease_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory and mount it for static file serving
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="api_uploads")


# Helper Functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)


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
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return serialize_doc(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Pydantic Models
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)


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


# ==================== API ROUTES ====================

# Health Check
@app.get("/api")
async def health_check():
    return {"status": "ok", "message": "RentEase API is running"}


# ==================== AUTH ROUTES ====================

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new user"""
    print(f"[REGISTER] {req}")
    # Check if user already exists
    existing_user = await db.users.find_one({"email": req.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user_doc = {
        "_id": ObjectId(),
        "name": req.name,
        "email": req.email,
        "password": hash_password(req.password),
        "role": None,  # Role will be selected later
        "createdAt": datetime.now(timezone.utc)
    }
    
    await db.users.insert_one(user_doc)
    
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


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login user"""
    print(f"[LOGIN] {req}")
    # Find user
    user = await db.users.find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create token
    token = create_token(str(user["_id"]))
    
    # Return user data without password
    user_data = serialize_doc(user)
    user_data.pop("password", None)
    
    return {
        "success": True,
        "token": token,
        "user": user_data,
        "requiresRoleSelection": user_data.get("role") is None
    }


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
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join("uploads", unique_filename)
        
        # Save file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Return file URL
        file_url = f"/uploads/{unique_filename}"
        
        return {
            "success": True,
            "url": file_url,
            "filename": unique_filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


# ==================== WISHLIST ROUTES ====================

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

