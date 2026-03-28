"""
RentEase - Rental Marketplace API
FastAPI Backend with MongoDB - Fixed bcrypt/validation
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
from pydantic import BaseModel
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

# Password hashing - FIXED bcrypt
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

# CORS - FIXED for localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# Helper Functions - FIXED bcrypt pw length
def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])  # bcrypt max 72 bytes


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


# Pydantic Models - RELAXED validation
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# Simple endpoints for testing
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    print(f"[REGISTER] {req}")
    try:
        existing = await db.users.find_one({"email": req.email})
        if existing:
            return {"success": False, "message": "Email exists"}
        
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
        user_data.pop("password")
        
        return {
            "success": True,
            "token": token,
            "user": user_data
        }
    except Exception as e:
        print(f"[REGISTER ERROR] {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    print(f"[LOGIN] {req}")
    try:
        user = await db.users.find_one({"email": req.email})
        if not user or not verify_password(req.password, user["password"]):
            return {"success": False, "message": "Invalid credentials"}
        
        token = create_token(str(user["_id"]))
        user_data = serialize_doc(user)
        user_data.pop("password")
        
        return {
            "success": True,
            "token": token,
            "user": user_data
        }
    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return {"success": False, "message": str(e)}


@app.get("/api")
async def health_check():
    return {"status": "ok", "message": "API ready"}


print("Fixed server ready!")
