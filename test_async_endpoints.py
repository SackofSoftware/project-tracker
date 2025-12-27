#!/usr/bin/env python3
"""
Test script for async scope analysis endpoints

This script tests the new async endpoints:
- Division 8 analysis: analyze, status, result
- Drawings analysis: analyze, status, result
"""

import requests
import time
import json

BASE_URL = "http://localhost:5003"

def test_async_endpoint(project_id, endpoint_type):
    """
    Test an async endpoint (division8 or drawings)

    Args:
        project_id: The project ID to analyze
        endpoint_type: Either 'division8' or 'drawings'
    """
    print(f"\n{'='*60}")
    print(f"Testing {endpoint_type} async analysis for project: {project_id}")
    print(f"{'='*60}\n")

    # Step 1: Start the analysis
    start_url = f"{BASE_URL}/api/project/{project_id}/scope/{endpoint_type}/analyze"
    print(f"1. Starting analysis: POST {start_url}")

    response = requests.post(start_url)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code != 200:
        print(f"\n   ERROR: Failed to start analysis")
        return

    # Step 2: Poll status until complete
    status_url = f"{BASE_URL}/api/project/{project_id}/scope/{endpoint_type}/status"
    print(f"\n2. Polling status: GET {status_url}")

    max_attempts = 60  # 60 seconds max
    for i in range(max_attempts):
        time.sleep(1)
        response = requests.get(status_url)
        status_data = response.json()

        status = status_data.get('status')
        progress = status_data.get('progress', 0)

        print(f"   Attempt {i+1}: status={status}, progress={progress:.0%}")

        if status == 'complete':
            print(f"\n   SUCCESS: Analysis completed!")
            break
        elif status == 'error':
            print(f"\n   ERROR: Analysis failed")
            print(f"   Error: {status_data.get('error')}")
            return
    else:
        print(f"\n   TIMEOUT: Analysis did not complete in {max_attempts} seconds")
        return

    # Step 3: Get the result
    result_url = f"{BASE_URL}/api/project/{project_id}/scope/{endpoint_type}/result"
    print(f"\n3. Getting result: GET {result_url}")

    response = requests.get(result_url)
    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"   Result summary:")

        if endpoint_type == 'division8':
            print(f"     - Project: {result.get('project_name')}")
            print(f"     - Spec files found: {result.get('spec_files_found')}")
            print(f"     - Spec files processed: {result.get('spec_files_processed')}")

            scope = result.get('division8_scope', [])
            if scope:
                print(f"     - Division 8 sections found: {len(scope)}")
                for item in scope:
                    if 'error' not in item:
                        print(f"       * {item.get('source_file')}: {len(item.get('sections', []))} sections")
            else:
                print(f"     - No Division 8 scope found")

        elif endpoint_type == 'drawings':
            print(f"     - Project: {result.get('project_name')}")
            print(f"     - Drawing files found: {result.get('drawing_files_found')}")

            summary = result.get('summary', {})
            if summary:
                print(f"     - Total sheets: {summary.get('total_sheets', 0)}")
                disciplines = summary.get('by_discipline', {})
                if disciplines:
                    print(f"     - Disciplines found:")
                    for disc, count in disciplines.items():
                        print(f"       * {disc}: {count} sheets")

            sheets = result.get('sheets', [])
            if sheets:
                print(f"     - Sheet details: {len(sheets)} sheets")
    else:
        print(f"   ERROR: {response.json()}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 test_async_endpoints.py <project_id> [endpoint_type]")
        print("  project_id: The project ID to test")
        print("  endpoint_type: 'division8' or 'drawings' or 'both' (default: both)")
        sys.exit(1)

    project_id = sys.argv[1]
    endpoint_type = sys.argv[2] if len(sys.argv) > 2 else 'both'

    try:
        if endpoint_type in ['division8', 'both']:
            test_async_endpoint(project_id, 'division8')

        if endpoint_type in ['drawings', 'both']:
            test_async_endpoint(project_id, 'drawings')

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
