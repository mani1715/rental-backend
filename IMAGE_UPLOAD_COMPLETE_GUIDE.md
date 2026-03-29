# Complete Image Upload Implementation Guide

## ✅ Current Setup (FastAPI Backend)

Your backend is **Python FastAPI**, not Node.js/Express. Here's how it works:

### 1. Static File Serving (Lines 85-88 in server.py)
```python
# Create uploads directory
os.makedirs("uploads", exist_ok=True)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="api_uploads")
```

### 2. Upload Endpoint (POST /api/upload)
```python
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload a file (images for listings)"""
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Check file size (max 5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join("uploads", unique_filename)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Return file URL
    file_url = f"/uploads/{unique_filename}"
    
    return {
        "success": True,
        "url": file_url,  # THIS is what you store in DB
        "filename": unique_filename,
        "size": len(content)
    }
```

### 3. Listing Model (Lines 262-276)
```python
class ListingCreate(BaseModel):
    title: str
    type: str
    price: float
    # ... other fields ...
    images: List[str] = []  # Array of image URLs like ["/uploads/abc123.jpg"]
```

### 4. Create Listing (POST /api/listings)
```python
@app.post("/api/listings")
async def create_listing(listing: ListingCreate, current_user: dict = Depends(get_current_user)):
    listing_doc = {
        "_id": ObjectId(),
        **listing.dict(),  # This includes the images array
        "ownerId": current_user["id"],
        "createdAt": datetime.now(timezone.utc),
    }
    
    await db.listings.insert_one(listing_doc)
    return {"success": True, "listing": serialize_doc(listing_doc)}
```

---

## How To Use (Frontend)

### Step 1: Upload Image
```javascript
const uploadImage = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch(`${API_URL}/api/upload`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });
  
  const data = await response.json();
  // Returns: { success: true, url: "/uploads/abc-123.jpg", filename: "abc-123.jpg", size: 12345 }
  
  return data.url;  // "/uploads/abc-123.jpg"
};
```

### Step 2: Create Listing with Image
```javascript
const createListing = async (listingData, imageFiles) => {
  // Upload all images first
  const imageUrls = [];
  for (const file of imageFiles) {
    const url = await uploadImage(file);
    imageUrls.push(url);
  }
  
  // Create listing with image URLs
  const response = await fetch(`${API_URL}/api/listings`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ...listingData,
      images: imageUrls  // ["/uploads/abc.jpg", "/uploads/def.jpg"]
    })
  });
  
  return await response.json();
};
```

### Step 3: Display Images
```jsx
const ListingImage = ({ imageUrl }) => {
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
  
  // Construct full URL
  const fullUrl = imageUrl.startsWith('http') 
    ? imageUrl 
    : `${BACKEND_URL}${imageUrl}`;
  
  return <img src={fullUrl} alt="Listing" />;
};

// Example usage:
<ListingImage imageUrl="/uploads/abc-123.jpg" />
// Renders: <img src="https://backend.com/uploads/abc-123.jpg" />
```

---

## Database Storage

### Correct Format:
```json
{
  "_id": ObjectId("..."),
  "title": "Beautiful House",
  "images": [
    "/uploads/abc-123.jpg",
    "/uploads/def-456.jpg"
  ]
}
```

### ❌ Wrong Format:
```json
{
  "images": ["C:\\fakepath\\house.jpg"]  // Wrong!
  "images": [null]  // Wrong!
  "images": []  // Empty!
}
```

---

## Testing

### 1. Upload Image
```bash
curl -X POST https://backend.com/api/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@house.jpg"
```

Response:
```json
{
  "success": true,
  "url": "/uploads/7a591e62-d4e3-43b9-b2cc-66c74e77f968.jpg",
  "filename": "7a591e62-d4e3-43b9-b2cc-66c74e77f968.jpg",
  "size": 245678
}
```

### 2. Access Image
```
Open in browser:
https://rental-backend-production-3c03.up.railway.app/uploads/7a591e62-d4e3-43b9-b2cc-66c74e77f968.jpg

Should display the image!
```

### 3. Create Listing
```bash
curl -X POST https://backend.com/api/listings \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Beautiful House",
    "type": "house",
    "price": 2000,
    "addressText": "123 Main St",
    "images": ["/uploads/7a591e62-d4e3-43b9-b2cc-66c74e77f968.jpg"],
    "bedrooms": 3,
    "bathrooms": 2
  }'
```

---

## Common Issues & Solutions

### Issue 1: Images not displaying

**Check 1: Verify image URL format**
```javascript
// Correct
const imageUrl = "/uploads/abc-123.jpg";
const fullUrl = `${BACKEND_URL}${imageUrl}`;
// Result: "https://backend.com/uploads/abc-123.jpg"

// Wrong
const imageUrl = "C:\\fakepath\\house.jpg";  // Browser file path!
```

**Check 2: Verify backend URL**
```javascript
// .env file
REACT_APP_BACKEND_URL=https://rental-backend-production-3c03.up.railway.app

// Usage
const fullUrl = `${process.env.REACT_APP_BACKEND_URL}/uploads/abc.jpg`;
```

**Check 3: Check if image exists**
```bash
# List uploaded files
curl https://backend.com/api/test-image
```

### Issue 2: Upload fails

**Check: File size**
- Maximum: 5MB
- If larger, compress before uploading

**Check: File type**
- Allowed: jpeg, jpg, png, gif, webp
- Not allowed: pdf, doc, etc.

### Issue 3: CORS error

**Solution: CORS is already configured**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rental-frontend-production-1987.up.railway.app"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)
```

---

## Summary

✅ **Upload endpoint**: POST /api/upload
✅ **Returns**: `{ url: "/uploads/filename.jpg" }`
✅ **Store in DB**: Array of URLs in `images` field
✅ **Access images**: `https://backend.com/uploads/filename.jpg`
✅ **Static serving**: Configured at /uploads
✅ **File validation**: Type and size checked
✅ **Unique filenames**: UUID-based

**Everything is already implemented and working!** 🚀
