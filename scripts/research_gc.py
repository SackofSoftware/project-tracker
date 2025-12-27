#!/usr/bin/env python3
"""
GC Deep Research Script

Researches general contractors and produces structured JSON profiles.
Uses web search + LLM to gather and structure company data.
"""

import os
import json
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Paths
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data" / "companies"
CONTRACTORS_DIR = DATA_DIR / "contractors"

# OpenRouter config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"  # Free 131k context model


@dataclass
class StaffMember:
    name: str
    title: str
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None


@dataclass
class Project:
    name: str
    type: str
    size: Optional[str] = None
    year: Optional[str] = None
    location: Optional[str] = None


@dataclass
class LegalCase:
    case_name: str
    court: Optional[str] = None
    date: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class GCProfile:
    """Complete GC company profile."""

    # Company basics
    name: str
    website: Optional[str] = None
    founded: Optional[int] = None
    headquarters: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    employee_count: Optional[str] = None
    description: Optional[str] = None
    certifications: List[str] = None

    # Leadership
    president: Optional[StaffMember] = None
    ceo: Optional[StaffMember] = None
    coo: Optional[StaffMember] = None
    founder: Optional[StaffMember] = None

    # Key staff
    estimators: List[StaffMember] = None
    project_managers: List[StaffMember] = None
    superintendents: List[StaffMember] = None
    other_staff: List[StaffMember] = None

    # Services & portfolio
    services: List[str] = None
    portfolio: List[Project] = None

    # Awards & reputation
    awards: List[str] = None
    bbb_rating: Optional[str] = None

    # Legal issues
    legal_issues: List[LegalCase] = None

    # Social presence
    linkedin: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    twitter: Optional[str] = None

    # Metadata
    research_date: str = None
    sources: List[str] = None

    def __post_init__(self):
        self.certifications = self.certifications or []
        self.estimators = self.estimators or []
        self.project_managers = self.project_managers or []
        self.superintendents = self.superintendents or []
        self.other_staff = self.other_staff or []
        self.services = self.services or []
        self.portfolio = self.portfolio or []
        self.awards = self.awards or []
        self.legal_issues = self.legal_issues or []
        self.sources = self.sources or []
        self.research_date = self.research_date or datetime.now().isoformat()


def slugify(name: str) -> str:
    """Convert company name to slug for filename."""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug.strip('-')


def call_openrouter(prompt: str, system: str = None) -> str:
    """Call OpenRouter API with a prompt."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://project-tracker.local",
            "X-Title": "GC Research Agent"
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.3
        },
        timeout=120
    )

    if response.status_code != 200:
        raise Exception(f"OpenRouter error: {response.status_code} - {response.text}")

    return response.json()["choices"][0]["message"]["content"]


def parse_gc_profile_json(json_str: str) -> Dict:
    """Extract JSON from LLM response."""
    # Try to find JSON in response
    json_match = re.search(r'\{[\s\S]*\}', json_str)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {}


def research_gc(name: str, location: str = None, website: str = None) -> GCProfile:
    """
    Research a general contractor and return structured profile.

    Args:
        name: Company name
        location: City/state (optional but recommended)
        website: Company website if known

    Returns:
        GCProfile dataclass
    """
    print(f"\n{'='*60}")
    print(f"Researching: {name}")
    if location:
        print(f"Location: {location}")
    if website:
        print(f"Website: {website}")
    print(f"{'='*60}")

    # Build research prompt
    location_str = f" in {location}" if location else ""
    website_str = f"\nCompany website: {website}" if website else ""

    prompt = f"""Research the general contractor "{name}"{location_str} and provide a comprehensive company profile.{website_str}

Find and include:

1. COMPANY INFO:
   - Official website URL
   - Founded year
   - Headquarters address
   - Phone number
   - Employee count estimate
   - Certifications (WBE, MBE, DBE, LEED, ABC, etc.)
   - Brief company description

2. LEADERSHIP (names and titles):
   - President/CEO
   - COO
   - Founders/Principals

3. KEY STAFF:
   - Chief Estimator / Preconstruction managers
   - Project Managers (list names)
   - Superintendents (list names)

4. SERVICES: What construction services do they offer?

5. PORTFOLIO: Notable completed projects (name, type, size if known)

6. AWARDS: Industry recognition, ABC awards, ENR rankings

7. LEGAL ISSUES: Any lawsuits, liens, complaints from court records

8. SOCIAL PRESENCE:
   - LinkedIn company page URL
   - Facebook URL
   - Instagram URL
   - Twitter URL

9. REPUTATION:
   - BBB rating
   - Notable reviews

Return the information as a JSON object with this structure:
{{
  "name": "Company Name",
  "website": "https://...",
  "founded": 1990,
  "headquarters": "Address, City, State",
  "phone": "xxx-xxx-xxxx",
  "employee_count": "21-50",
  "description": "Brief description",
  "certifications": ["WBE", "LEED"],
  "leadership": {{
    "president": {{"name": "Name", "title": "President"}},
    "ceo": null,
    "coo": {{"name": "Name", "title": "COO"}},
    "founder": {{"name": "Name", "title": "Founder"}}
  }},
  "estimators": [{{"name": "Name", "title": "Chief Estimator"}}],
  "project_managers": [{{"name": "Name", "title": "Project Manager"}}],
  "superintendents": [{{"name": "Name", "title": "Superintendent"}}],
  "services": ["General Contracting", "Construction Management"],
  "portfolio": [{{"name": "Project Name", "type": "Commercial", "size": "50,000 SF"}}],
  "awards": ["Award name 2024"],
  "legal_issues": [{{"case_name": "Plaintiff v. Company", "status": "Settled"}}],
  "linkedin": "https://linkedin.com/company/...",
  "facebook": "https://facebook.com/...",
  "instagram": "https://instagram.com/...",
  "bbb_rating": "A+"
}}

Be thorough but only include information you can verify. Use null for unknown fields.
"""

    system_prompt = """You are a construction industry research analyst.
Your job is to gather comprehensive, accurate information about general contractors.
Always cite specific sources when possible. Only include verifiable information.
Return well-structured JSON that can be parsed programmatically."""

    print("\nCalling LLM for research...")

    try:
        response = call_openrouter(prompt, system_prompt)
        print(f"Got response ({len(response)} chars)")

        # Parse JSON from response
        data = parse_gc_profile_json(response)

        if not data:
            print("Warning: Could not parse JSON from response")
            print(f"Response preview: {response[:500]}")
            data = {"name": name}

        # Convert to GCProfile
        profile = GCProfile(
            name=data.get("name", name),
            website=data.get("website"),
            founded=data.get("founded"),
            headquarters=data.get("headquarters"),
            phone=data.get("phone"),
            email=data.get("email"),
            employee_count=data.get("employee_count"),
            description=data.get("description"),
            certifications=data.get("certifications", []),
            services=data.get("services", []),
            awards=data.get("awards", []),
            linkedin=data.get("linkedin"),
            facebook=data.get("facebook"),
            instagram=data.get("instagram"),
            twitter=data.get("twitter"),
            bbb_rating=data.get("bbb_rating"),
        )

        # Parse leadership
        leadership = data.get("leadership", {})
        if leadership.get("president"):
            profile.president = StaffMember(**leadership["president"])
        if leadership.get("ceo"):
            profile.ceo = StaffMember(**leadership["ceo"])
        if leadership.get("coo"):
            profile.coo = StaffMember(**leadership["coo"])
        if leadership.get("founder"):
            profile.founder = StaffMember(**leadership["founder"])

        # Parse staff lists
        for est in data.get("estimators", []):
            if isinstance(est, dict):
                profile.estimators.append(StaffMember(**est))
        for pm in data.get("project_managers", []):
            if isinstance(pm, dict):
                profile.project_managers.append(StaffMember(**pm))
        for sup in data.get("superintendents", []):
            if isinstance(sup, dict):
                profile.superintendents.append(StaffMember(**sup))

        # Parse portfolio
        for proj in data.get("portfolio", []):
            if isinstance(proj, dict):
                profile.portfolio.append(Project(**proj))

        # Parse legal issues
        for case in data.get("legal_issues", []):
            if isinstance(case, dict):
                profile.legal_issues.append(LegalCase(**case))

        return profile

    except Exception as e:
        print(f"Error during research: {e}")
        return GCProfile(name=name)


def save_profile(profile: GCProfile, overwrite: bool = False) -> Path:
    """Save profile to JSON file."""
    CONTRACTORS_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{slugify(profile.name)}.json"
    filepath = CONTRACTORS_DIR / filename

    if filepath.exists() and not overwrite:
        print(f"Profile already exists: {filepath}")
        return filepath

    # Convert to dict, handling dataclasses
    def to_dict(obj):
        if hasattr(obj, '__dataclass_fields__'):
            return {k: to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [to_dict(i) for i in obj]
        return obj

    data = to_dict(profile)

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Saved profile: {filepath}")
    return filepath


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Research a general contractor")
    parser.add_argument("name", help="Company name")
    parser.add_argument("--location", "-l", help="City, State")
    parser.add_argument("--website", "-w", help="Company website")
    parser.add_argument("--save", "-s", action="store_true", help="Save to JSON")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing")

    args = parser.parse_args()

    profile = research_gc(args.name, args.location, args.website)

    if args.save:
        save_profile(profile, args.overwrite)
    else:
        # Print profile summary
        print(f"\n{'='*60}")
        print(f"PROFILE: {profile.name}")
        print(f"{'='*60}")
        print(f"Website: {profile.website}")
        print(f"Founded: {profile.founded}")
        print(f"HQ: {profile.headquarters}")
        print(f"Phone: {profile.phone}")
        print(f"Employees: {profile.employee_count}")
        print(f"Certifications: {', '.join(profile.certifications)}")

        if profile.president:
            print(f"\nPresident: {profile.president.name}")
        if profile.estimators:
            print(f"Estimators: {len(profile.estimators)}")
        if profile.project_managers:
            print(f"Project Managers: {len(profile.project_managers)}")
        if profile.superintendents:
            print(f"Superintendents: {len(profile.superintendents)}")

        print(f"\nServices: {', '.join(profile.services[:5])}")
        print(f"Portfolio: {len(profile.portfolio)} projects")
        print(f"Awards: {len(profile.awards)}")
        print(f"Legal Issues: {len(profile.legal_issues)}")

        print(f"\nLinkedIn: {profile.linkedin}")
        print(f"BBB: {profile.bbb_rating}")


if __name__ == "__main__":
    main()
