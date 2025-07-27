#!/usr/bin/env python3
"""
Test script for the MLK Archive Search application
"""
import requests
import json
from app import app

def test_search_api():
    """Test the search API endpoint"""
    with app.test_client() as client:
        # Test basic search
        response = client.get('/search?q=FBI')
        data = response.get_json()
        
        print("=== Search API Test ===")
        print(f"Status Code: {response.status_code}")
        print(f"Total Results: {data.get('total', 0)}")
        print(f"Results Returned: {len(data.get('results', []))}")
        
        if data.get('results'):
            first_result = data['results'][0]
            print(f"First Result ID: {first_result.get('element_id', 'N/A')[:20]}...")
            print(f"First Result Context: {first_result.get('context', 'N/A')[:100]}...")
            print(f"PDF URL: {first_result.get('pdf_url', 'N/A')}")
        
        print()
        
        # Test phrase search
        response = client.get('/search?q="Eric Galt"')
        data = response.get_json()
        
        print("=== Phrase Search Test ===")
        print(f"Status Code: {response.status_code}")
        print(f"Total Results: {data.get('total', 0)}")
        print(f"Results Returned: {len(data.get('results', []))}")
        
        print()
        
        # Test health endpoint
        response = client.get('/health')
        data = response.get_json()
        
        print("=== Health Check ===")
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Database: {data.get('database', 'unknown')}")

if __name__ == "__main__":
    test_search_api()