"""
Division 08 Scope Analyzer for Construction Glazing Contractors
Specifically designed to extract doors, windows, storefront, curtainwall, mirrors, and hardware
"""

import re
import json
from typing import List, Dict, Optional
from rag_document_parser import DocumentParser


class Division08Analyzer:
    """
    Specialized analyzer for Division 08 scope extraction
    Focuses on: Hollow metal doors, metal doors, aluminum doors, windows,
                storefront, curtainwall, bathroom mirrors, hardware, glazing
    Excludes: Wood doors, overhead doors
    """

    def __init__(self, persist_directory="./chroma_db"):
        self.parser = DocumentParser(persist_directory)

        # Division 08 spec sections we care about
        self.target_specs = {
            '081113': 'Hollow Metal Doors and Frames',
            '081216': 'Aluminum Doors and Frames',
            '081416': 'Flush Wood Doors',  # EXCLUDE
            '082113': 'Plastic Doors',
            '082813': 'Overhead Coiling Doors',  # EXCLUDE
            '083113': 'Access Doors',
            '084113': 'Aluminum-Framed Entrances and Storefronts',
            '084213': 'Sliding Aluminum-Framed Entrances',
            '084313': 'Revolving Door Entrances',
            '084413': 'Glazed Aluminum Curtain Walls',
            '085113': 'Metal Windows',
            '085213': 'Aluminum Windows',
            '085313': 'Vinyl Windows',
            '087100': 'Door Hardware',
            '088000': 'Glazing',
            '088300': 'Mirrors',
        }

        # Sections to EXCLUDE from scope
        self.excluded_specs = [
            '081416',  # Wood doors
            '082813',  # Overhead doors
            '083313',  # Rolling doors
        ]

    def find_division_08_specs(self, project_name: str) -> List[Dict]:
        """Query for all Division 08 specification sections"""

        queries = [
            "SECTION 081113 Hollow Metal Doors",
            "SECTION 081216 Aluminum Doors",
            "SECTION 084113 Storefront",
            "SECTION 084413 Curtain Wall",
            "SECTION 085213 Aluminum Windows",
            "SECTION 087100 Door Hardware",
            "SECTION 088000 Glazing",
            "SECTION 088300 Mirrors",
            "Division 08 specifications openings"
        ]

        all_results = {}

        for query in queries:
            results = self.parser.query(project_name, query, n_results=5)

            for result in results:
                # Extract section numbers
                text = result['text']
                sections = re.findall(r'SECTION\s*(\d{5,6})\s*[-–]?\s*([A-Z][A-Za-z\s&,/\-]+)', text)

                for section_num, section_title in sections:
                    if section_num.startswith('08'):
                        # Check if excluded
                        if section_num not in self.excluded_specs:
                            if section_num not in all_results:
                                all_results[section_num] = {
                                    'section': section_num,
                                    'title': section_title.strip(),
                                    'source_file': result['metadata'].get('source_file'),
                                    'page': result['metadata'].get('page'),
                                    'in_scope': section_num not in self.excluded_specs
                                }

        return list(all_results.values())

    def find_door_schedules(self, project_name: str) -> List[Dict]:
        """Find door schedules in drawings"""

        queries = [
            "door schedule hollow metal aluminum",
            "door type door mark door number schedule",
            "door elevations details"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                # Focus on drawing files
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')

                    if page not in seen_pages:
                        text = result['text']

                        # Look for schedule indicators
                        if re.search(r'DOOR\s+SCHEDULE|SCHEDULE.*DOOR|DOOR.*TYPE.*MARK', text, re.IGNORECASE):
                            results.append({
                                'type': 'door_schedule',
                                'source_file': result['metadata'].get('source_file'),
                                'sheet': result['metadata'].get('sheet_number'),
                                'page': page,
                                'text_sample': text[:300]
                            })
                            seen_pages.add(page)

        return results

    def find_window_schedules(self, project_name: str) -> List[Dict]:
        """Find window schedules and elevations in drawings"""

        queries = [
            "window schedule elevations",
            "window type glazing dimensions",
            "aluminum window schedule"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')

                    if page not in seen_pages:
                        text = result['text']

                        # Look for window schedule/elevation indicators
                        if re.search(r'WINDOW\s+(SCHEDULE|ELEVATION|TYPE|DETAIL)', text, re.IGNORECASE):
                            results.append({
                                'type': 'window_schedule',
                                'source_file': result['metadata'].get('source_file'),
                                'sheet': result['metadata'].get('sheet_number'),
                                'page': page,
                                'text_sample': text[:300]
                            })
                            seen_pages.add(page)

        return results

    def find_storefront_curtainwall(self, project_name: str) -> List[Dict]:
        """Find storefront and curtainwall schedules/elevations"""

        queries = [
            "storefront elevation schedule details",
            "curtain wall curtainwall elevation",
            "aluminum storefront system"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')

                    if page not in seen_pages:
                        text = result['text']

                        # Look for storefront/curtainwall indicators
                        if re.search(r'STOREFRONT|CURTAIN\s*WALL', text, re.IGNORECASE):

                            # Determine type
                            item_type = 'storefront' if 'STOREFRONT' in text.upper() else 'curtainwall'

                            results.append({
                                'type': item_type,
                                'source_file': result['metadata'].get('source_file'),
                                'sheet': result['metadata'].get('sheet_number'),
                                'page': page,
                                'text_sample': text[:300]
                            })
                            seen_pages.add(page)

        return results

    def find_hardware_schedule(self, project_name: str) -> List[Dict]:
        """Find hardware schedules (may be in specs OR drawings)"""

        queries = [
            "hardware schedule door hardware set",
            "hardware group door set",
            "hinges locksets closers hardware"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                page = result['metadata'].get('page')

                if page not in seen_pages:
                    text = result['text']

                    # Look for hardware schedule indicators
                    if re.search(r'HARDWARE\s+(SCHEDULE|SET|GROUP)|SET:\s*\d+', text, re.IGNORECASE):
                        results.append({
                            'type': 'hardware_schedule',
                            'source_file': result['metadata'].get('source_file'),
                            'document_type': result['metadata'].get('document_type'),
                            'page': page,
                            'text_sample': text[:300]
                        })
                        seen_pages.add(page)

        return results

    def find_glazing_schedule(self, project_name: str) -> List[Dict]:
        """Find glazing schedules (typically in drawings)"""

        queries = [
            "glazing schedule glass type",
            "glazing legend glass thickness",
            "glass schedule IGU"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')

                    if page not in seen_pages:
                        text = result['text']

                        if re.search(r'GLAZ(ING|E)\s+(SCHEDULE|LEGEND|TYPE)|GLASS\s+SCHEDULE', text, re.IGNORECASE):
                            results.append({
                                'type': 'glazing_schedule',
                                'source_file': result['metadata'].get('source_file'),
                                'sheet': result['metadata'].get('sheet_number'),
                                'page': page,
                                'text_sample': text[:300]
                            })
                            seen_pages.add(page)

        return results

    def find_exterior_elevations(self, project_name: str) -> List[Dict]:
        """Find exterior elevation sheets"""

        queries = [
            "exterior elevation north south east west",
            "building elevation"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=15)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')
                    sheet = result['metadata'].get('sheet_number', '')

                    if page not in seen_pages:
                        text = result['text']

                        # Look for elevation indicators (A3.x sheets typically)
                        if re.search(r'ELEVATION|ELEV\.|A3[-.]?\d+', text, re.IGNORECASE):
                            # Exclude reflected ceiling plans
                            if not re.search(r'REFLECTED\s+CEILING|RCP', text, re.IGNORECASE):
                                results.append({
                                    'type': 'exterior_elevation',
                                    'source_file': result['metadata'].get('source_file'),
                                    'sheet': sheet,
                                    'page': page,
                                    'text_sample': text[:200]
                                })
                                seen_pages.add(page)

        return results

    def find_floor_plans(self, project_name: str) -> List[Dict]:
        """Find floor plans (excluding reflected ceiling plans)"""

        queries = [
            "floor plan first floor second floor",
            "plan level"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=15)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')
                    sheet = result['metadata'].get('sheet_number', '')
                    text = result['text']

                    if page not in seen_pages:
                        # EXCLUDE reflected ceiling plans
                        if not re.search(r'REFLECTED\s+CEILING|RCP|CEILING\s+PLAN', text, re.IGNORECASE):
                            # Look for floor plan indicators
                            if re.search(r'FLOOR\s+PLAN|PLAN.*FLOOR|LEVEL\s+\d+|A2[-.]?\d+', text, re.IGNORECASE):
                                results.append({
                                    'type': 'floor_plan',
                                    'source_file': result['metadata'].get('source_file'),
                                    'sheet': sheet,
                                    'page': page,
                                    'text_sample': text[:200]
                                })
                                seen_pages.add(page)

        return results

    def find_detail_pages(self, project_name: str) -> List[Dict]:
        """Find relevant detail pages for Division 08 scope"""

        queries = [
            "door detail jamb head sill",
            "window detail frame",
            "storefront detail section",
            "curtainwall detail mullion",
            "glazing detail"
        ]

        results = []
        seen_pages = set()

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=10)

            for result in search_results:
                if result['metadata'].get('document_type') == 'drawing':
                    page = result['metadata'].get('page')

                    if page not in seen_pages:
                        text = result['text']

                        if re.search(r'DETAIL|SECTION|A[45][-.]?\d+', text, re.IGNORECASE):
                            results.append({
                                'type': 'detail_page',
                                'source_file': result['metadata'].get('source_file'),
                                'sheet': result['metadata'].get('sheet_number'),
                                'page': page,
                                'text_sample': text[:200]
                            })
                            seen_pages.add(page)

        return results

    def find_mirrors(self, project_name: str) -> List[Dict]:
        """Find bathroom mirror specifications and callouts"""

        queries = [
            "mirror bathroom restroom",
            "mirrors mounting"
        ]

        results = []

        for query in queries:
            search_results = self.parser.query(project_name, query, n_results=5)

            for result in search_results:
                text = result['text']

                if re.search(r'MIRROR', text, re.IGNORECASE):
                    results.append({
                        'type': 'mirrors',
                        'source_file': result['metadata'].get('source_file'),
                        'document_type': result['metadata'].get('document_type'),
                        'page': result['metadata'].get('page'),
                        'text_sample': text[:300]
                    })

        return results

    def analyze_project(self, project_name: str) -> Dict:
        """
        Complete Division 08 scope analysis
        Returns comprehensive report of all relevant items
        """

        print(f"\n{'='*80}")
        print(f"DIVISION 08 SCOPE ANALYSIS: {project_name}")
        print(f"{'='*80}\n")

        report = {
            'project_name': project_name,
            'specifications': {
                'division_08_sections': [],
                'excluded_sections': []
            },
            'drawings': {
                'door_schedules': [],
                'window_schedules': [],
                'storefront': [],
                'curtainwall': [],
                'glazing_schedules': [],
                'hardware_schedules': [],
                'exterior_elevations': [],
                'floor_plans': [],
                'detail_pages': [],
                'mirrors': []
            }
        }

        # 1. Specifications Analysis
        print("1. Analyzing Specifications...")
        specs = self.find_division_08_specs(project_name)

        for spec in specs:
            if spec['in_scope']:
                report['specifications']['division_08_sections'].append(spec)
            else:
                report['specifications']['excluded_sections'].append(spec)

        print(f"   Found {len(report['specifications']['division_08_sections'])} Division 08 sections in scope")
        print(f"   Excluded {len(report['specifications']['excluded_sections'])} sections (wood doors, overhead doors)")

        # 2. Door Schedules
        print("\n2. Searching for Door Schedules...")
        report['drawings']['door_schedules'] = self.find_door_schedules(project_name)
        print(f"   Found {len(report['drawings']['door_schedules'])} door schedule pages")

        # 3. Window Schedules
        print("\n3. Searching for Window Schedules/Elevations...")
        report['drawings']['window_schedules'] = self.find_window_schedules(project_name)
        print(f"   Found {len(report['drawings']['window_schedules'])} window schedule/elevation pages")

        # 4. Storefront & Curtainwall
        print("\n4. Searching for Storefront/Curtainwall...")
        sf_cw = self.find_storefront_curtainwall(project_name)
        for item in sf_cw:
            if item['type'] == 'storefront':
                report['drawings']['storefront'].append(item)
            else:
                report['drawings']['curtainwall'].append(item)
        print(f"   Found {len(report['drawings']['storefront'])} storefront pages")
        print(f"   Found {len(report['drawings']['curtainwall'])} curtainwall pages")

        # 5. Hardware Schedule
        print("\n5. Searching for Hardware Schedules...")
        report['drawings']['hardware_schedules'] = self.find_hardware_schedule(project_name)
        print(f"   Found {len(report['drawings']['hardware_schedules'])} hardware schedule pages")

        # 6. Glazing Schedule
        print("\n6. Searching for Glazing Schedules...")
        report['drawings']['glazing_schedules'] = self.find_glazing_schedule(project_name)
        print(f"   Found {len(report['drawings']['glazing_schedules'])} glazing schedule pages")

        # 7. Exterior Elevations
        print("\n7. Searching for Exterior Elevations...")
        report['drawings']['exterior_elevations'] = self.find_exterior_elevations(project_name)
        print(f"   Found {len(report['drawings']['exterior_elevations'])} exterior elevation sheets")

        # 8. Floor Plans
        print("\n8. Searching for Floor Plans...")
        report['drawings']['floor_plans'] = self.find_floor_plans(project_name)
        print(f"   Found {len(report['drawings']['floor_plans'])} floor plan sheets")

        # 9. Detail Pages
        print("\n9. Searching for Detail Pages...")
        report['drawings']['detail_pages'] = self.find_detail_pages(project_name)
        print(f"   Found {len(report['drawings']['detail_pages'])} detail pages")

        # 10. Mirrors
        print("\n10. Searching for Mirrors...")
        report['drawings']['mirrors'] = self.find_mirrors(project_name)
        print(f"   Found {len(report['drawings']['mirrors'])} mirror references")

        print(f"\n{'='*80}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*80}\n")

        return report

    def export_report(self, report: Dict, output_file: str):
        """Export report to JSON file"""
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report exported to: {output_file}")


# Example usage
if __name__ == "__main__":
    analyzer = Division08Analyzer()

    # Analyze Colt State Park project
    report = analyzer.analyze_project("Colt_State_Park")

    # Export report
    analyzer.export_report(report, "colt_state_park_division08_analysis.json")

    # Print summary
    print("\n" + "="*80)
    print("DIVISION 08 SCOPE SUMMARY")
    print("="*80)
    print(f"\nSpecifications:")
    for spec in report['specifications']['division_08_sections']:
        print(f"  • {spec['section']} - {spec['title']}")

    print(f"\nKey Drawing Sheets:")
    print(f"  • Door Schedules: {len(report['drawings']['door_schedules'])} sheets")
    print(f"  • Window Schedules: {len(report['drawings']['window_schedules'])} sheets")
    print(f"  • Storefront: {len(report['drawings']['storefront'])} sheets")
    print(f"  • Curtainwall: {len(report['drawings']['curtainwall'])} sheets")
    print(f"  • Hardware Schedules: {len(report['drawings']['hardware_schedules'])} locations")
    print(f"  • Glazing Schedules: {len(report['drawings']['glazing_schedules'])} sheets")
    print(f"  • Exterior Elevations: {len(report['drawings']['exterior_elevations'])} sheets")
    print(f"  • Floor Plans: {len(report['drawings']['floor_plans'])} sheets")
    print(f"  • Detail Pages: {len(report['drawings']['detail_pages'])} sheets")
