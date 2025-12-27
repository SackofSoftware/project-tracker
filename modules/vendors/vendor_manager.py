"""
Vendor Manager
Manages vendor database with CRUD operations and quote tracking
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class VendorManager:
    """Manages vendor database and operations"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vendors_file = self.data_dir / "vendors.json"
        self._vendors_data = self._load()

    def _load(self) -> Dict:
        """Load vendors data from file"""
        if self.vendors_file.exists():
            try:
                with open(self.vendors_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading vendors file: {e}")
        return {"vendors": {}, "updated_at": None}

    def _save(self):
        """Save vendors data to file"""
        self._vendors_data["updated_at"] = datetime.now().isoformat()
        with open(self.vendors_file, 'w') as f:
            json.dump(self._vendors_data, f, indent=2)

    def add_vendor(self, name: str, contact_name: str = None, email: str = None,
                   phone: str = None, specialty: List[str] = None, notes: str = None) -> Dict:
        """Add a new vendor"""
        vendor_id = str(uuid.uuid4())

        vendor = {
            "id": vendor_id,
            "name": name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "specialty": specialty or [],
            "notes": notes,
            "quotes": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        if "vendors" not in self._vendors_data:
            self._vendors_data["vendors"] = {}

        self._vendors_data["vendors"][vendor_id] = vendor
        self._save()

        return vendor

    def update_vendor(self, vendor_id: str, updates: Dict) -> Optional[Dict]:
        """Update an existing vendor"""
        if "vendors" not in self._vendors_data:
            return None

        vendor = self._vendors_data["vendors"].get(vendor_id)
        if not vendor:
            return None

        # Update allowed fields
        allowed_fields = ['name', 'contact_name', 'email', 'phone', 'specialty', 'notes']
        for field in allowed_fields:
            if field in updates:
                vendor[field] = updates[field]

        vendor["updated_at"] = datetime.now().isoformat()
        self._vendors_data["vendors"][vendor_id] = vendor
        self._save()

        return vendor

    def delete_vendor(self, vendor_id: str) -> bool:
        """Delete a vendor"""
        if "vendors" not in self._vendors_data:
            return False

        if vendor_id in self._vendors_data["vendors"]:
            del self._vendors_data["vendors"][vendor_id]
            self._save()
            return True

        return False

    def get_vendor(self, vendor_id: str) -> Optional[Dict]:
        """Get a single vendor by ID"""
        if "vendors" not in self._vendors_data:
            return None
        return self._vendors_data["vendors"].get(vendor_id)

    def get_all_vendors(self) -> List[Dict]:
        """Get all vendors"""
        if "vendors" not in self._vendors_data:
            return []

        vendors = list(self._vendors_data["vendors"].values())
        # Sort by name
        vendors.sort(key=lambda v: v.get('name', '').lower())
        return vendors

    def search_vendors(self, query: str) -> List[Dict]:
        """Search vendors by name, contact, or specialty"""
        all_vendors = self.get_all_vendors()
        query = query.lower()

        results = []
        for vendor in all_vendors:
            # Search in name
            if query in vendor.get('name', '').lower():
                results.append(vendor)
                continue

            # Search in contact name
            if vendor.get('contact_name') and query in vendor['contact_name'].lower():
                results.append(vendor)
                continue

            # Search in specialty
            if vendor.get('specialty'):
                for spec in vendor['specialty']:
                    if query in spec.lower():
                        results.append(vendor)
                        break

        return results

    def add_quote_to_vendor(self, vendor_id: str, project_id: str,
                           project_name: str = None, amount: float = None,
                           quote_date: str = None, notes: str = None,
                           source_file: str = None) -> Optional[Dict]:
        """Add a quote record to a vendor"""
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return None

        quote = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "project_name": project_name,
            "amount": amount,
            "quote_date": quote_date or datetime.now().isoformat(),
            "notes": notes,
            "source_file": source_file,
            "created_at": datetime.now().isoformat()
        }

        if "quotes" not in vendor:
            vendor["quotes"] = []

        vendor["quotes"].append(quote)
        vendor["updated_at"] = datetime.now().isoformat()

        self._vendors_data["vendors"][vendor_id] = vendor
        self._save()

        return quote

    def get_vendor_quotes(self, vendor_id: str) -> List[Dict]:
        """Get all quotes for a vendor"""
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return []

        quotes = vendor.get("quotes", [])
        # Sort by date, newest first
        quotes.sort(key=lambda q: q.get('quote_date', ''), reverse=True)
        return quotes

    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        vendors = self.get_all_vendors()

        total_vendors = len(vendors)
        total_quotes = sum(len(v.get('quotes', [])) for v in vendors)

        # Count by specialty
        specialty_counts = {}
        for vendor in vendors:
            for spec in vendor.get('specialty', []):
                specialty_counts[spec] = specialty_counts.get(spec, 0) + 1

        return {
            "total_vendors": total_vendors,
            "total_quotes": total_quotes,
            "by_specialty": specialty_counts
        }
