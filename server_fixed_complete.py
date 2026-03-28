"""
RentEase API - Complete Fixed Version
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Body
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

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "rentease_db")
JWT_SECRET = os.environ.get("JWT_SECRET", "rentease_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

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

app = FastAPI(title="RentEase API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def serialize_doc(doc: dict) -> dict:
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

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SelectRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(OWNER|CUSTOMER)$")

@app.get("/api")
async def health_check():
    return {"status": "ok", "message": "RentEase API is running"}

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    print(f"[REGISTER] {req}")
    existing_user = await db.users.find_one({"email": req.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "_id": ObjectId(),
        "name": req.name,
        "email": req.email,
        "password": hash_password(req.password),
        "role": None,
        "createdAt": datetime.now(timezone.utc)
    }
    
    await db.users.insert_one(user_doc)
    
    token = create_token(str(user_doc["_id"]))
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
    print(f"[LOGIN] {req}")
    user = await db.users.find_one({"email": req.email})
    if not user or not verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_token(str(user["_id"]))
    user_data = serialize_doc(user)
    user_data.pop("password", None)
    
    return {
        "success": True,
        "token": token,
        "user": user_data,
        "requiresRoleSelection": user_data.get("role") is None
    }

@app.get("/api/user/me")
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    return {"success": True, "user": current_user}

@app.post("/api/user/select-role")
async def select_role(req: SelectRoleRequest, current_user: dict = Depends(get_current_user)):
    result = await db.users.update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {"role": req.role}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update role")
    
    updated_user = await db.users.find_one({"_id": ObjectId(current_user["id"])})
    user_data = serialize_doc(updated_user)
    user_data.pop("password", None)
    
    return {"success": True, "user": user_data}

@app.get("/api/owner/profile")
async def get_owner_profile(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can access this endpoint")
    
    profile = await db.owner_profiles.find_one({"userId": current_user["id"]})
    if not profile:
        profile = {
            "_id": ObjectId(),
            "userId": current_user["id"],
            "bio": "",
            "phone": "",
            "createdAt": datetime.now(timezone.utc)
        }
        await db.owner_profiles.insert_one(profile)
    
    return {"success": True, "profile": serialize_doc(profile)}

@app.post("/api/owner/profile")
async def update_owner_profile(data: dict, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can access this endpoint")
    
    result = await db.owner_profiles.update_one(
        {"userId": current_user["id"]},
        {"$set": data},
        upsert=True
    )
    
    profile = await db.owner_profiles.find_one({"userId": current_user["id"]})
    return {"success": True, "profile": serialize_doc(profile)}

@app.get("/api/listings")
async def get_listings(ownerId: Optional[str] = None, type: Optional[str] = None):
    query = {}
    if ownerId:
        query["ownerId"] = ownerId
    if type:
        query["type"] = type
    listings = await db.listings.find(query).to_list(length=100)
    return {"success": True, "listings": [serialize_doc(l) for l in listings]}

print("Fixed complete server ready!")
