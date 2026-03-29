"""
Test AI Description Generation with Fallback
"""

class AIDescriptionRequest:
    def __init__(self, **kwargs):
        self.title = kwargs.get('title')
        self.location = kwargs.get('location')
        self.price = kwargs.get('price')
        self.propertyType = kwargs.get('propertyType')
        self.bedrooms = kwargs.get('bedrooms')
        self.bathrooms = kwargs.get('bathrooms')
        self.squareFeet = kwargs.get('squareFeet')

def generate_fallback_description(req) -> str:
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


# Test cases
test_cases = [
    {
        "title": "Luxury 2BR Apartment",
        "location": "Downtown Manhattan, NY",
        "price": 3500,
        "propertyType": "Apartment",
        "bedrooms": 2,
        "bathrooms": 2,
        "squareFeet": 1200
    },
    {
        "title": "Cozy Studio",
        "location": "Brooklyn Heights",
        "price": 1800,
        "propertyType": "Studio",
        "bedrooms": None,
        "bathrooms": 1,
        "squareFeet": 450
    },
    {
        "title": "Spacious House",
        "location": "Queens",
        "price": 4200,
        "propertyType": "House",
        "bedrooms": 4,
        "bathrooms": 3,
        "squareFeet": 2500
    }
]

print("="*80)
print("Testing Fallback Description Generator")
print("="*80)

for i, test_data in enumerate(test_cases, 1):
    print(f"\n{'='*80}")
    print(f"Test Case {i}: {test_data['title']}")
    print('='*80)
    
    req = AIDescriptionRequest(**test_data)
    description = generate_fallback_description(req)
    
    print(f"\n📍 Location: {test_data['location']}")
    print(f"💰 Price: ${test_data['price']:,.2f}")
    print(f"🏠 Type: {test_data['propertyType']}")
    if test_data['bedrooms']:
        print(f"🛏️  Bedrooms: {test_data['bedrooms']}")
    print(f"🚿 Bathrooms: {test_data['bathrooms']}")
    if test_data['squareFeet']:
        print(f"📐 Size: {test_data['squareFeet']:,.0f} sq ft")
    
    print(f"\n📝 Generated Description ({len(description)} chars):")
    print("-" * 80)
    print(description)
    print("-" * 80)
    
    # Verify description quality
    checks = {
        "Has location": test_data['location'] in description,
        "Has price": f"${test_data['price']:,.2f}" in description,
        "Has property type": test_data['propertyType'].lower() in description.lower(),
        "Reasonable length": 100 < len(description) < 500
    }
    
    print("\n✅ Quality Checks:")
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {check}")

print("\n" + "="*80)
print("All fallback descriptions generated successfully!")
print("="*80)
print("\n💡 These descriptions are used when Gemini API is unavailable")
print("   They provide professional, customized descriptions without AI")
