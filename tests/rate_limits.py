"""
Script to check your Gemini API rate limits
Run: python check_gemini_rate_limits.py
"""
import asyncio
import time
from google import genai
from pathlib import Path
import os

# Replace with your API key
API_KEY = os.getenv("GEMINI_API_KEY", "your-api-key-here")

async def test_concurrent_requests(num_requests=5):
    """Test how many concurrent requests your API key can handle"""
    
    print(f"🧪 Testing {num_requests} concurrent requests to Gemini API...")
    
    client = genai.Client(api_key=API_KEY)
    
    async def make_request(request_id):
        start = time.time()
        try:
            # Use thread pool for blocking call
            loop = asyncio.get_event_loop()
            
            def sync_call():
                return client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=["Generate a simple red circle"],
                    config={
                        "response_modalities": ["IMAGE"],
                        "image_config": {"aspect_ratio": "1:1"}
                    }
                )
            
            response = await loop.run_in_executor(None, sync_call)
            duration = time.time() - start
            
            print(f"✅ Request {request_id} completed in {duration:.2f}s")
            return True, duration
            
        except Exception as e:
            duration = time.time() - start
            print(f"❌ Request {request_id} failed in {duration:.2f}s: {str(e)}")
            return False, duration
    
    # Run all requests concurrently
    start_all = time.time()
    results = await asyncio.gather(*[make_request(i+1) for i in range(num_requests)])
    total_time = time.time() - start_all
    
    # Calculate stats
    successful = sum(1 for success, _ in results if success)
    failed = num_requests - successful
    avg_time = sum(duration for _, duration in results) / num_requests
    
    print("\n" + "="*50)
    print(f"📊 RESULTS:")
    print(f"   Total requests: {num_requests}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Average time per request: {avg_time:.2f}s")
    print(f"   Requests per second: {num_requests/total_time:.2f}")
    print("="*50)

async def check_api_info():
    """Get basic API information"""
    print("📋 Checking API Information...")
    
    try:
        client = genai.Client(api_key=API_KEY)
        
        # List available models
        print("\n🤖 Available models:")
        for model in client.models.list():
            print(f"   - {model.name}")
        
        print("\n✅ API Key is valid!")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

if __name__ == "__main__":
    print("🚀 Gemini API Rate Limit Checker\n")
    
    # First, verify API key works
    asyncio.run(check_api_info())
    
    print("\n" + "="*50 + "\n")
    
    # Test with increasing concurrent requests
    for num in [1, 3, 5, 10]:
        asyncio.run(test_concurrent_requests(num))
        print("\n")
        time.sleep(2)  # Wait between tests