"""
Database Module Example Usage

Demonstrates how to use the database module for common operations.
"""

from datetime import datetime, timedelta
from modules.database import db, queries
from modules.database.migrate import migrate_from_json


def example_basic_operations():
    """Example: Basic project operations"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Basic Project Operations")
    print("=" * 60)

    # Create a new project
    print("\n1. Creating a new project...")
    project = queries.create_project(
        project_id='example-school-project',
        data={
            'title': 'Example Elementary School',
            'address': '123 Main Street',
            'city': 'Boston',
            'state': 'MA',
            'source': 'local',
            'owner_name': 'Boston Public Schools',
            'architect_name': 'Smith & Associates',
            'bid_date': datetime.now() + timedelta(days=15),
            'estimated_value': '5M',
            'dcam_required': True,
            'prevailing_wage': True
        }
    )
    print(f"   Created: {project.id} - {project.title}")

    # Update project status
    print("\n2. Adding project status...")
    status = queries.create_or_update_status(
        project_id='example-school-project',
        data={
            'bid_decision': 'bid',
            'bid_decision_reason': 'Good fit for our capabilities, competitive pricing opportunity',
            'documents_acquired': True,
            'has_specs': True,
            'has_drawings': True,
            'estimate_created': True,
            'estimate_total': 235000.00,
            'windows_total': 85000.00,
            'doors_total': 95000.00,
            'hardware_total': 35000.00,
            'storefront_total': 20000.00
        }
    )
    print(f"   Status: {status.bid_decision} - ${status.estimate_total:,.2f}")

    # Add notes
    print("\n3. Adding project notes...")
    note1 = queries.add_project_note(
        'example-school-project',
        'Called architect about window schedule clarification',
        note_type='estimate'
    )
    note2 = queries.add_project_note(
        'example-school-project',
        'Pre-bid meeting scheduled for next Tuesday at 10am',
        note_type='general'
    )
    print(f"   Added {2} notes")

    # Add tags
    print("\n4. Adding tags...")
    queries.add_project_tag('example-school-project', 'school')
    queries.add_project_tag('example-school-project', 'dcam')
    queries.add_project_tag('example-school-project', 'high-priority')
    print(f"   Added 3 tags")

    # Add competitors
    print("\n5. Adding competitors...")
    queries.add_competitor(
        'example-school-project',
        company_name='ABC Glass & Glazing',
        contact_name='John Doe'
    )
    queries.add_competitor(
        'example-school-project',
        company_name='XYZ Window Systems',
        notes='Strong competitor, usually prices aggressively'
    )
    print(f"   Added 2 competitors")


def example_vendor_operations():
    """Example: Vendor and quote operations"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Vendor & Quote Operations")
    print("=" * 60)

    # Create vendors
    print("\n1. Creating vendors...")
    vendor1 = queries.get_or_create_vendor(
        name='Superior Windows Inc',
        vendor_data={
            'contact_name': 'Mike Johnson',
            'email': 'mike@superiorwindows.com',
            'phone': '617-555-1234',
            'city': 'Worcester',
            'state': 'MA',
            'company_type': 'manufacturer',
            'specialties': ['windows', 'storefront', 'curtain_wall']
        }
    )

    vendor2 = queries.get_or_create_vendor(
        name='Best Door Company',
        vendor_data={
            'contact_name': 'Sarah Smith',
            'email': 'sarah@bestdoor.com',
            'phone': '508-555-5678',
            'city': 'Boston',
            'state': 'MA',
            'company_type': 'distributor',
            'specialties': ['doors', 'frames', 'hardware']
        }
    )

    print(f"   Created: {vendor1.name}")
    print(f"   Created: {vendor2.name}")

    # Add quotes
    print("\n2. Adding vendor quotes...")
    quote1 = queries.add_vendor_quote({
        'project_id': 'example-school-project',
        'vendor_id': vendor1.id,
        'category': 'windows',
        'amount': 42000.00,
        'quote_date': datetime.now(),
        'status': 'received',
        'notes': 'Aluminum double-hung windows, includes installation'
    })

    quote2 = queries.add_vendor_quote({
        'project_id': 'example-school-project',
        'vendor_id': vendor2.id,
        'category': 'doors',
        'amount': 58000.00,
        'quantity': 45,
        'unit': 'ea',
        'unit_price': 1288.89,
        'quote_date': datetime.now(),
        'status': 'received',
        'notes': 'Hollow metal doors with frames, fire-rated assemblies'
    })

    print(f"   Quote 1: {vendor1.name} - ${quote1.amount:,.2f}")
    print(f"   Quote 2: {vendor2.name} - ${quote2.amount:,.2f}")


def example_division8_scope():
    """Example: Division 8 scope analysis"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Division 8 Scope Analysis")
    print("=" * 60)

    print("\n1. Saving Division 8 scope analysis...")
    scope = queries.save_division8_scope(
        project_id='example-school-project',
        scope_data={
            'scope_summary': 'Project includes aluminum windows, hollow metal doors and frames, '
                           'aluminum storefront, door hardware, and glazing.',
            'confidence': 'high',
            'windows_count': '85 units',
            'windows_types': ['Aluminum double-hung', 'Fixed aluminum', 'Projected aluminum'],
            'windows_notes': 'Mix of operable and fixed units, various sizes per schedule',
            'metal_door_count': '45 doors',
            'wood_door_count': '0 (excluded from scope)',
            'doors_notes': 'Hollow metal doors and frames, multiple fire ratings required',
            'storefront_description': 'Aluminum storefront at main entrance, approximately 120 SF',
            'storefront_sf_estimate': '120',
            'hardware_groups': ['Hinges', 'Locksets', 'Exit devices', 'Closers', 'Stops'],
            'hardware_manufacturers': ['Corbin Russwin', 'Von Duprin', 'LCN'],
            'glass_specs': ['1/4" insulated glass', '1/4" tempered glass', 'Fire-rated glass at rated assemblies'],
            'exclusions': ['Wood doors', 'Interior finishes', 'Signage'],
            'embedder_model': 'ollama-nomic-embed-text',
            'generator_model': 'gpt-4o-mini',
            'chunks_analyzed': 42,
            'total_chunks': 250,
            'tokens_used': 8500,
            'generated_at': datetime.now()
        }
    )

    print(f"   Scope summary: {scope.scope_summary[:80]}...")
    print(f"   Windows: {scope.windows_count}")
    print(f"   Doors: {scope.metal_door_count}")
    print(f"   Confidence: {scope.confidence}")


def example_file_operations():
    """Example: File classification operations"""
    print("\n" + "=" * 60)
    print("EXAMPLE: File Classification")
    print("=" * 60)

    print("\n1. Adding file classifications...")
    files = queries.bulk_add_files(
        project_id='example-school-project',
        files_data=[
            {
                'name': 'Architectural Drawings.pdf',
                'path': '/path/to/drawings.pdf',
                'file_type': 'drawing_set',
                'pages': 48,
                'size_mb': 12.5,
                'confidence': 0.95,
                'classified_by': 'heuristic'
            },
            {
                'name': 'Specifications - Division 08.pdf',
                'path': '/path/to/specs.pdf',
                'file_type': 'specification',
                'pages': 156,
                'size_mb': 3.2,
                'confidence': 0.98,
                'classified_by': 'heuristic'
            },
            {
                'name': 'Window Schedule.pdf',
                'path': '/path/to/window_schedule.pdf',
                'file_type': 'schedule',
                'pages': 4,
                'size_mb': 0.8,
                'confidence': 0.90,
                'classified_by': 'llm'
            },
            {
                'name': 'Addendum 1.pdf',
                'path': '/path/to/addendum1.pdf',
                'file_type': 'addendum',
                'pages': 8,
                'size_mb': 1.1,
                'confidence': 0.85,
                'classified_by': 'heuristic'
            }
        ]
    )

    print(f"   Classified {len(files)} files")
    for f in files:
        print(f"   - {f.name} ({f.file_type}, {f.pages} pages, {f.size_mb} MB)")


def example_queries():
    """Example: Various query operations"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Query Operations")
    print("=" * 60)

    # Get project
    print("\n1. Get specific project...")
    project = queries.get_project('example-school-project')
    if project:
        print(f"   Found: {project.title}")
        print(f"   Address: {project.address}, {project.city}, {project.state}")
        print(f"   Bid Date: {project.bid_date.strftime('%Y-%m-%d') if project.bid_date else 'N/A'}")

    # Get project with status
    print("\n2. Get project status...")
    status = queries.get_project_status('example-school-project')
    if status:
        print(f"   Bid Decision: {status.bid_decision}")
        print(f"   Estimate Total: ${status.estimate_total:,.2f}" if status.estimate_total else "   No estimate yet")

    # Get project files
    print("\n3. Get project files...")
    files = queries.get_project_files('example-school-project')
    print(f"   Found {len(files)} files")

    # Get drawings only
    drawings = queries.get_project_files('example-school-project', file_type='drawing_set')
    print(f"   Found {len(drawings)} drawing sets")

    # Get Division 8 scope
    print("\n4. Get Division 8 scope...")
    scope = queries.get_division8_scope('example-school-project')
    if scope:
        print(f"   Windows: {scope.windows_count}")
        print(f"   Doors: {scope.metal_door_count}")
        print(f"   Hardware groups: {len(scope.hardware_groups) if scope.hardware_groups else 0}")

    # Get quotes
    print("\n5. Get vendor quotes...")
    quotes = queries.get_project_quotes('example-school-project')
    print(f"   Found {len(quotes)} quotes")
    total_quoted = sum(q.amount for q in quotes if q.amount)
    print(f"   Total quoted: ${total_quoted:,.2f}")

    # Get notes
    print("\n6. Get project notes...")
    notes = queries.get_project_notes('example-school-project')
    print(f"   Found {len(notes)} notes")
    for note in notes:
        print(f"   - [{note.note_type}] {note.content[:60]}...")


def example_search_and_filter():
    """Example: Search and filter operations"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Search & Filter")
    print("=" * 60)

    # Get all projects
    print("\n1. Get all projects...")
    all_projects = queries.get_all_projects()
    print(f"   Total projects: {len(all_projects)}")

    # Get upcoming projects
    print("\n2. Get upcoming bids (next 30 days)...")
    upcoming = queries.get_upcoming_projects(days=30)
    print(f"   Upcoming bids: {len(upcoming)}")
    for proj in upcoming[:3]:  # Show first 3
        bid_date = proj.bid_date.strftime('%Y-%m-%d') if proj.bid_date else 'N/A'
        print(f"   - {proj.title} (Bid: {bid_date})")

    # Search projects
    print("\n3. Search projects...")
    results = queries.search_projects('school')
    print(f"   Found {len(results)} projects matching 'school'")

    # Get by source
    print("\n4. Get projects by source...")
    local = queries.get_projects_by_source('local')
    print(f"   Local projects: {len(local)}")


def example_statistics():
    """Example: Dashboard statistics"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Dashboard Statistics")
    print("=" * 60)

    stats = queries.get_dashboard_stats()

    print("\nDashboard Statistics:")
    print(f"  Total Projects:           {stats['total_projects']}")
    print(f"  Local Projects:           {stats['local_projects']}")
    print(f"  ProjectDog Projects:      {stats['projectdog_projects']}")
    print(f"  Upcoming Bids:            {stats['upcoming_bids']}")
    print(f"  Projects with Estimates:  {stats['projects_with_estimates']}")
    print(f"  Projects with Scope:      {stats['projects_with_scope']}")
    print(f"  Active Vendors:           {stats['vendors_count']}")
    print(f"  Total Quotes:             {stats['total_quotes']}")


def example_database_health():
    """Example: Database health check"""
    print("\n" + "=" * 60)
    print("EXAMPLE: Database Health Check")
    print("=" * 60)

    health = db.check_database()

    print(f"\nStatus:     {health['status']}")
    print(f"Path:       {health['path']}")
    print(f"Tables:     {health['table_count']}")
    print(f"Connection: {health['connection']}")

    if health.get('tables'):
        print("\nDatabase Tables:")
        for table in sorted(health['tables']):
            print(f"  - {table}")


def run_all_examples():
    """Run all examples"""
    print("\n" + "=" * 70)
    print("PROJECT TRACKER DATABASE MODULE - EXAMPLES")
    print("=" * 70)

    # Initialize database
    print("\nInitializing database...")
    db.init_db()
    print("Database initialized!")

    # Run examples
    example_basic_operations()
    example_vendor_operations()
    example_division8_scope()
    example_file_operations()
    example_queries()
    example_search_and_filter()
    example_statistics()
    example_database_health()

    print("\n" + "=" * 70)
    print("EXAMPLES COMPLETE")
    print("=" * 70)
    print(f"\nDatabase location: {db.get_db_path()}")
    print("\nTo clean up the example project, run:")
    print("  from modules.database import queries")
    print("  queries.delete_project('example-school-project')")
    print()


if __name__ == '__main__':
    run_all_examples()
