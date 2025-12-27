# Vendor Tracking System

## Overview

The Vendor Tracking System is a complete vendor management solution integrated into the Project Tracker application. It allows you to track vendors, contacts, specialties, and quote history all in one place.

## Features

- **Complete CRUD Operations**: Create, read, update, and delete vendors
- **Contact Management**: Store contact names, emails, and phone numbers
- **Specialty Tracking**: Tag vendors with their areas of expertise (windows, doors, hardware, etc.)
- **Quote History**: Track all quotes received from each vendor by project
- **Search & Filter**: Quickly find vendors by name, contact, or specialty
- **Statistics Dashboard**: View total vendors, quotes, and specialty breakdowns

## File Structure

```
modules/vendors/
├── __init__.py                 # Module exports
└── vendor_manager.py           # Core vendor management logic

static/data/
└── vendors.json                # JSON database file

templates/
└── vendors.html                # Vendor management UI
```

## Data Schema

### Vendor Object
```json
{
  "id": "uuid",
  "name": "TWI Supply",
  "contact_name": "John Smith",
  "email": "john@twi.com",
  "phone": "555-1234",
  "specialty": ["windows", "doors", "storefronts"],
  "notes": "Good pricing on fiberglass",
  "quotes": [...],
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

### Quote Object
```json
{
  "id": "uuid",
  "project_id": "PROJ-001",
  "project_name": "Sample School Project",
  "amount": 15000.50,
  "quote_date": "2025-01-01T00:00:00",
  "notes": "Aluminum storefront quote",
  "created_at": "2025-01-01T00:00:00"
}
```

## API Endpoints

### GET /api/vendors
Get all vendors with statistics
```bash
curl http://localhost:5003/api/vendors
```

### POST /api/vendors
Create a new vendor
```bash
curl -X POST http://localhost:5003/api/vendors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Vendor",
    "contact_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-9999",
    "specialty": ["windows", "doors"],
    "notes": "Great pricing"
  }'
```

### GET /api/vendors/<vendor_id>
Get a single vendor by ID
```bash
curl http://localhost:5003/api/vendors/<vendor_id>
```

### PUT /api/vendors/<vendor_id>
Update a vendor
```bash
curl -X PUT http://localhost:5003/api/vendors/<vendor_id> \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "555-8888",
    "notes": "Updated notes"
  }'
```

### DELETE /api/vendors/<vendor_id>
Delete a vendor
```bash
curl -X DELETE http://localhost:5003/api/vendors/<vendor_id>
```

### POST /api/vendors/<vendor_id>/quotes
Add a quote to a vendor
```bash
curl -X POST http://localhost:5003/api/vendors/<vendor_id>/quotes \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJ-123",
    "project_name": "New School",
    "amount": 25000.00,
    "quote_date": "2025-01-15",
    "notes": "Includes installation"
  }'
```

### GET /api/vendors/search?q=<query>
Search vendors
```bash
curl http://localhost:5003/api/vendors/search?q=windows
```

## Usage

### Accessing the Vendor Management Page

1. Start the Project Tracker: `python3 app.py`
2. Navigate to: `http://localhost:5003/vendors`
3. Or click the "Vendors" button in the dashboard header

### Adding a Vendor

1. Click "Add Vendor" button
2. Fill in vendor details:
   - Name (required)
   - Contact name
   - Email
   - Phone
   - Specialties (type and press Enter to add multiple)
   - Notes
3. Click "Save Vendor"

### Adding Quotes

1. Find the vendor in the list
2. Click "Add Quote" button
3. Enter quote details:
   - Project ID
   - Project name
   - Amount
   - Quote date
   - Notes
4. Click "Add Quote"

### Searching Vendors

Use the search bar at the top to filter vendors by:
- Vendor name
- Contact name
- Specialty tags
- Email address

### Viewing Quote History

Click on any vendor row to expand and view:
- Full contact information
- All specialties
- Complete quote history with amounts and dates

## VendorManager Class

The `VendorManager` class handles all vendor operations:

```python
from modules.vendors import VendorManager

# Initialize
vm = VendorManager("static/data")

# Add vendor
vendor = vm.add_vendor(
    name="Example Vendor",
    contact_name="John Doe",
    email="john@example.com",
    phone="555-1234",
    specialty=["windows", "doors"],
    notes="Great service"
)

# Get all vendors
vendors = vm.get_all_vendors()

# Search vendors
results = vm.search_vendors("windows")

# Add quote
quote = vm.add_quote_to_vendor(
    vendor_id=vendor['id'],
    project_id="PROJ-001",
    project_name="Sample Project",
    amount=15000.00,
    notes="Initial quote"
)

# Get statistics
stats = vm.get_summary_stats()
```

## Integration with Projects

The vendor system can be integrated with project tracking:

1. When receiving a quote, use the "Add Quote" feature to record it
2. Quote amounts can be compared to internal estimates
3. Track which vendors quote on which types of projects
4. Build a history of vendor reliability and pricing

## Sample Data

The system includes 5 sample vendors with 6 sample quotes:

- **TWI Supply**: Windows, doors, storefronts
- **Aluminum Depot**: Storefront, curtain wall, glazing
- **Hardware Solutions Inc**: Hardware, door closers, panic devices
- **Glass & Glazing Co**: Glazing, glass, mirrors
- **Metropolitan Door Company**: Doors, frames, hardware

## Future Enhancements

Possible improvements:
- Link quotes directly to project tracker entries
- Export vendor/quote data to CSV/Excel
- Vendor performance ratings
- Email integration for quote requests
- File attachment support for quote PDFs
- Automatic quote comparison by project
- Vendor contact history timeline
