#!/usr/bin/env python3
"""
Portkey AI Gateway Embeddings Test Script
A CLI tool to test embeddings models through the Portkey AI gateway.
"""

import sys
import time
from typing import List, Optional
from portkey_ai import Portkey


def print_banner():
    """Print a fancy banner because why not."""
    print("\n" + "="*60)
    print("🔢 Portkey AI Gateway Embeddings Tester")
    print("="*60 + "\n")


def get_api_key() -> str:
    """Prompt user for Portkey API key."""
    api_key = input("Enter your Portkey API key: ").strip()
    if not api_key:
        print("❌ Error: API key cannot be empty.")
        sys.exit(1)
    return api_key


def get_config_id() -> Optional[str]:
    """Prompt user for optional config ID."""
    config_id = input("Enter config ID (optional, press Enter to skip): ").strip()
    return config_id if config_id else None


def get_model_slugs() -> List[str]:
    """Prompt user for embeddings model slugs (comma-separated)."""
    models_input = input("Enter embeddings model slugs (comma-separated): ").strip()
    if not models_input:
        print("❌ Error: At least one embeddings model slug is required.")
        sys.exit(1)
    
    # Split by comma and clean up whitespace
    model_slugs = [slug.strip() for slug in models_input.split(',') if slug.strip()]
    
    if not model_slugs:
        print("❌ Error: No valid model slugs provided.")
        sys.exit(1)
    
    return model_slugs


def get_test_texts() -> List[str]:
    """Prompt user for test texts to embed."""
    print("\nEnter text(s) to embed (one per line, empty line to finish):")
    texts = []
    while True:
        text = input(f"  Text {len(texts) + 1}: ").strip()
        if not text:
            break
        texts.append(text)
    
    if not texts:
        # Use default test texts
        texts = ["Hello, world!", "Testing embeddings through Portkey"]
        print(f"  Using default texts: {texts}")
    
    return texts


def test_embeddings_model(client: Portkey, model_slug: str, texts: List[str]) -> bool:
    """
    Test a single embeddings model by sending an embeddings request.
    
    Args:
        client: Initialized Portkey client
        model_slug: Embeddings model identifier to test
        texts: List of texts to embed
    
    Returns:
        True if test successful, False otherwise
    """
    print(f"\n🧪 Testing embeddings model: {model_slug}")
    print("-" * 60)
    
    try:
        # Measure response time
        start_time = time.time()
        
        # Send embeddings request
        response = client.embeddings.create(
            input=texts,
            model=model_slug
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Check for successful response
        if response and hasattr(response, 'data') and len(response.data) > 0:
            print(f"✅ Embeddings Success! API Key is working.")
            print(f"   Requested model: {model_slug}")
            
            # Show model information
            actual_model = response.model if hasattr(response, 'model') else 'Unknown'
            print(f"   Response from model: {actual_model}")
            print(f"   ⏱️  Response time: {response_time:.2f}s")
            print(f"   ➜ Please verify this is the correct routing for your config.")
            print(f"")
            
            # Show embeddings info
            num_embeddings = len(response.data)
            print(f"   Number of embeddings: {num_embeddings}")
            
            if num_embeddings > 0:
                first_embedding = response.data[0].embedding
                embedding_dim = len(first_embedding) if isinstance(first_embedding, list) else 'Unknown'
                print(f"   Embedding dimensions: {embedding_dim}")
                
                # Show a preview of the first embedding vector
                if isinstance(first_embedding, list) and len(first_embedding) > 0:
                    preview = first_embedding[:5]  # First 5 dimensions
                    preview_str = ", ".join([f"{v:.4f}" for v in preview])
                    print(f"   Sample (first 5 dims): [{preview_str}...]")
            
            # Show usage if available
            if hasattr(response, 'usage'):
                print(f"   Tokens used: {response.usage}")
            
            return True
        else:
            print(f"❌ Failed: Invalid response structure")
            print(f"   Response: {response}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        
        # Check for HTTP-related error attributes
        if hasattr(e, 'status_code'):
            print(f"   HTTP Status: {e.status_code}")
        
        # Get response body if available (avoid duplication with error.body)
        if hasattr(e, 'response') and not hasattr(e, 'body'):
            try:
                response_body = e.response
                if hasattr(response_body, 'text'):
                    print(f"   Response Body: {response_body.text[:500]}")  # First 500 chars
                elif hasattr(response_body, 'json'):
                    print(f"   Response JSON: {response_body.json()}")
                else:
                    print(f"   Response: {str(response_body)[:500]}")
            except:
                pass
        
        # Check for Portkey-specific error metadata (prioritize this over response)
        if hasattr(e, 'body') and e.body:
            print(f"   Details: {e.body}")
        
        # Show additional error attributes (but skip 'message' to avoid duplication)
        error_attrs = ['code', 'type', 'param']
        for attr in error_attrs:
            if hasattr(e, attr) and getattr(e, attr):
                print(f"   {attr.capitalize()}: {getattr(e, attr)}")
        
        return False


def main():
    """Main execution flow."""
    print_banner()
    
    # Get user inputs
    api_key = get_api_key()
    config_id = get_config_id()
    model_slugs = get_model_slugs()
    test_texts = get_test_texts()
    
    # Initialize Portkey client
    print(f"\n🔧 Initializing Portkey client...")
    
    client_kwargs = {"api_key": api_key}
    if config_id:
        client_kwargs["config"] = config_id
        print(f"   Using config ID: {config_id}")
    
    client = Portkey(**client_kwargs)
    
    # Test each model
    print(f"\n📊 Testing {len(model_slugs)} embeddings model(s) with {len(test_texts)} text(s)...")
    
    results = {}
    for model_slug in model_slugs:
        results[model_slug] = test_embeddings_model(client, model_slug, test_texts)
    
    # Summary
    print("\n" + "="*60)
    print("📋 TEST SUMMARY")
    print("="*60)
    
    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful
    
    for model, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {model}")
    
    print(f"\nTotal: {successful} passed, {failed} failed")
    print("="*60 + "\n")
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(130)

