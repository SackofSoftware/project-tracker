#!/usr/bin/env python3
"""
Test script for the new project brief endpoint
"""
import requests
import json

def test_brief_endpoint():
    base_url = "http://localhost:5003"

    # Test 1: Get brief in JSON format
    print("TEST 1: JSON format brief for 21-27-neptune")
    print("=" * 60)
    response = requests.get(f"{base_url}/api/project/21-27-neptune/brief?use_lm_studio=false")

    if response.status_code == 200:
        data = response.json()
        print(f"✓ Status: {data['status']}")
        print(f"✓ Project: {data['project_name']}")
        print(f"✓ Errors: {len(data['context']['errors'])}")
        print(f"✓ Windows found: {data['context']['openings_data']['total_windows']}")
        print(f"✓ Doors found: {data['context']['openings_data']['total_doors']}")
        print(f"✓ Has quotes: {data['context']['quotes_data']['has_quotes']}")
        if data['context']['quotes_data']['has_quotes']:
            print(f"✓ Quote value: ${data['context']['quotes_data']['total_value']:,.2f}")
        print()
    else:
        print(f"✗ Error: {response.status_code}")
        print(response.text)
        return False

    # Test 2: Get brief in text format
    print("TEST 2: Text format brief for gardner-school-hingham")
    print("=" * 60)
    response = requests.get(f"{base_url}/api/project/gardner-school-hingham/brief?format=text&use_lm_studio=false")

    if response.status_code == 200:
        text = response.text
        print("✓ Generated brief preview:")
        print(text[:500])
        print("...")
        print()
    else:
        print(f"✗ Error: {response.status_code}")
        return False

    # Test 3: Test with non-existent project
    print("TEST 3: Non-existent project")
    print("=" * 60)
    response = requests.get(f"{base_url}/api/project/nonexistent-project/brief")

    if response.status_code == 404:
        print("✓ Correctly returned 404 for non-existent project")
        print()
    else:
        print(f"✗ Expected 404, got {response.status_code}")
        return False

    # Test 4: Test LM Studio flag (will fallback if not running)
    print("TEST 4: Test with use_lm_studio=true (will fallback)")
    print("=" * 60)
    response = requests.get(f"{base_url}/api/project/21-27-neptune/brief?use_lm_studio=true")

    if response.status_code == 200:
        data = response.json()
        print(f"✓ Successfully generated brief (using fallback)")
        print()
    else:
        print(f"✗ Error: {response.status_code}")
        return False

    print("=" * 60)
    print("All tests passed! ✓")
    print()
    print("USAGE EXAMPLES:")
    print("-" * 60)
    print(f"# Get brief in JSON format:")
    print(f"curl {base_url}/api/project/21-27-neptune/brief")
    print()
    print(f"# Get brief in plain text:")
    print(f"curl {base_url}/api/project/21-27-neptune/brief?format=text")
    print()
    print(f"# Force OpenRouter (skip LM Studio):")
    print(f"curl {base_url}/api/project/21-27-neptune/brief?force_openrouter=true")
    print()
    print(f"# Use LM Studio if available:")
    print(f"curl {base_url}/api/project/21-27-neptune/brief?use_lm_studio=true")

    return True

if __name__ == "__main__":
    test_brief_endpoint()
