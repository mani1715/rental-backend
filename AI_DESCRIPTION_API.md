# AI Description Generator API

## Endpoint
`POST /api/ai/generate-description`

## Description
Generates professional property descriptions using Google Gemini AI based on property details.

## Request Body
```json
{
  "title": "Luxury 2BR Apartment",
  "location": "Downtown Manhattan, NY",
  "price": 3500,
  "propertyType": "Apartment",  // Optional
  "bedrooms": 2,                 // Optional
  "bathrooms": 2,                // Optional
  "squareFeet": 1200            // Optional
}
```

## Response
```json
{
  "success": true,
  "description": "Welcome to this stunning 2-bedroom apartment nestled in the heart of Downtown Manhattan. This beautifully appointed residence offers 1200 square feet of modern living space, featuring 2 well-designed bathrooms and contemporary finishes throughout. The open-concept layout maximizes natural light and creates an inviting atmosphere perfect for both relaxation and entertaining.\n\nLocated in one of Manhattan's most vibrant neighborhoods, residents enjoy unparalleled access to world-class dining, shopping, and entertainment. The area's excellent public transportation connections make commuting a breeze, while nearby parks provide peaceful green spaces for leisure activities.\n\nThis exceptional apartment represents an ideal opportunity for those seeking the ultimate urban lifestyle. With its combination of prime location, modern amenities, and thoughtful design, this property offers everything you need for comfortable city living."
}
```

## Error Responses

### 503 Service Unavailable
```json
{
  "detail": "AI service not configured. Please set GEMINI_API_KEY environment variable."
}
```

### 500 Internal Server Error
```json
{
  "detail": "AI generation failed: [error details]"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "title"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Setup

1. Get a Gemini API key from: https://makersuite.google.com/app/apikey

2. Add to `.env` file:
```bash
GEMINI_API_KEY=your_api_key_here
```

3. Restart the backend server

## Frontend Example

```javascript
const generateDescription = async (propertyData) => {
  try {
    const response = await fetch(`${API_URL}/api/ai/generate-description`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        title: propertyData.title,
        location: propertyData.location,
        price: propertyData.price,
        propertyType: propertyData.type,
        bedrooms: propertyData.bedrooms,
        bathrooms: propertyData.bathrooms,
        squareFeet: propertyData.squareFeet
      })
    });
    
    const data = await response.json();
    
    if (data.success) {
      return data.description;
    } else {
      throw new Error('AI generation failed');
    }
  } catch (error) {
    console.error('Error generating description:', error);
    throw error;
  }
};
```

## Features

✅ Professional 2-3 paragraph descriptions
✅ 150-200 words optimized for readability
✅ Highlights key features and location benefits
✅ Friendly yet professional tone
✅ No markdown formatting (plain text)
✅ Customizes based on provided property details

## Notes

- The AI generates unique descriptions each time
- More property details provided = better descriptions
- No pricing or contact info included in generated text
- Generated text is ready to use directly in listings
