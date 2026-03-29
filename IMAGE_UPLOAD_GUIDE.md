# Image Upload & Serving Guide

## Upload Endpoint

**POST** `/api/upload`

### Authentication
Requires authentication token in header:
```
Authorization: Bearer <token>
```

### Request
- **Method:** POST
- **Content-Type:** multipart/form-data
- **Body:** File with key `file`

### Allowed File Types
- image/jpeg
- image/jpg
- image/png
- image/gif
- image/webp

### Max File Size
5 MB (5,242,880 bytes)

### Response
```json
{
  "success": true,
  "url": "/uploads/123e4567-e89b-12d3-a456-426614174000.jpg",
  "filename": "123e4567-e89b-12d3-a456-426614174000.jpg",
  "size": 102400
}
```

### Error Responses

**400 - Invalid File Type:**
```json
{
  "detail": "Invalid file type. Allowed: image/jpeg, image/jpg, image/png, image/gif, image/webp"
}
```

**400 - File Too Large:**
```json
{
  "detail": "File too large. Max size: 5MB"
}
```

**401 - Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

## Accessing Uploaded Images

### URL Format
```
https://your-domain.com/uploads/filename.jpg
```

### Example
If upload returns:
```json
{
  "url": "/uploads/abc123.jpg"
}
```

Access at:
```
https://rental-backend-production-3c03.up.railway.app/uploads/abc123.jpg
```

## Static File Serving

### Configured Routes
1. `/uploads/*` - Direct access to uploaded files
2. `/api/uploads/*` - Alternative access path

### Examples
```
✅ https://backend.com/uploads/image.jpg
✅ https://backend.com/api/uploads/image.jpg
```

## Frontend Usage

### Upload Image
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
  
  if (data.success) {
    return data.url;  // "/uploads/abc123.jpg"
  } else {
    throw new Error('Upload failed');
  }
};
```

### Display Image
```javascript
// Construct full URL
const imageUrl = `${API_URL}${data.url}`;

// Use in img tag
<img src={imageUrl} alt="Property" />

// Or if backend URL is configured correctly
<img src={data.url} alt="Property" />
```

### React Example
```jsx
const PropertyImage = ({ imageUrl }) => {
  const API_BASE_URL = process.env.REACT_APP_BACKEND_URL;
  
  // If imageUrl is relative (starts with /)
  const fullUrl = imageUrl.startsWith('http') 
    ? imageUrl 
    : `${API_BASE_URL}${imageUrl}`;
  
  return (
    <img 
      src={fullUrl} 
      alt="Property"
      onError={(e) => {
        e.target.src = '/placeholder-image.jpg';
        console.error('Image failed to load:', fullUrl);
      }}
    />
  );
};
```

## Testing

### Test Upload (curl)
```bash
curl -X POST \
  https://your-backend.com/api/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

### Test Image Access
```bash
# Direct access
curl https://your-backend.com/uploads/abc123.jpg

# Should return image file
```

### Test Image Serving
```
GET /api/test-image
```

Response:
```json
{
  "success": true,
  "uploadsDirectory": "uploads",
  "directoryExists": true,
  "totalFiles": 5,
  "imageFiles": 5,
  "sampleImages": ["abc123.jpg", "def456.jpg"],
  "sampleUrls": ["/uploads/abc123.jpg", "/uploads/def456.jpg"]
}
```

## Troubleshooting

### Issue: Images not displaying

**Check 1: Verify upload succeeded**
```javascript
console.log('Upload response:', data);
// Should have: { success: true, url: "/uploads/..." }
```

**Check 2: Verify URL is correct**
```javascript
const fullUrl = `${BACKEND_URL}${imageUrl}`;
console.log('Full image URL:', fullUrl);
// Should be: https://backend.com/uploads/abc123.jpg
```

**Check 3: Test direct access**
```
Open in browser: https://backend.com/uploads/abc123.jpg
Should display image or download it
```

**Check 4: Check CORS**
```javascript
// Image requests should not be blocked by CORS
// Backend CORS is configured to allow all origins for static files
```

**Check 5: Check file exists on server**
```
GET /api/test-image
// Verify file is in the list
```

### Issue: Upload fails

**Check 1: File type**
- Must be: jpeg, jpg, png, gif, or webp

**Check 2: File size**
- Must be under 5MB

**Check 3: Authentication**
- Must include valid Bearer token

**Check 4: Form data key**
- Must use key name: `file`

## Logs

Server logs will show:
```
[UPLOAD] ═══════════════════════════════════════════
[UPLOAD] User: user@example.com
[UPLOAD] Filename: my-image.jpg
[UPLOAD] Content Type: image/jpeg
[UPLOAD] File size: 245.67 KB
[UPLOAD] Saving to: uploads/abc123.jpg
[UPLOAD] ✅ File saved successfully (245.67 KB)
[UPLOAD] URL: /uploads/abc123.jpg
```

## Security

- ✅ Authentication required
- ✅ File type validation
- ✅ File size limits
- ✅ Unique filenames (UUID)
- ✅ Secure file storage
- ✅ No directory traversal
