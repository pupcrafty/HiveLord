"""Test DomBot with actual OpenAI API request."""
import asyncio
import json
from app.ai.dom_bot import DomBot
from app.ai.contracts import get_response_schema

async def test_dom_bot():
    """Test DomBot with a real request."""
    print("=" * 60)
    print("Testing DomBot with OpenAI API")
    print("=" * 60)
    
    # Check schema first
    schema = get_response_schema()
    print("\n1. Schema validation:")
    print(f"   - Schema keys: {list(schema.keys())}")
    print(f"   - Has $defs: {'$defs' in schema}")
    print(f"   - Has $ref: {json.dumps(schema).find('$ref') != -1}")
    print(f"   - Has anyOf: {json.dumps(schema).find('anyOf') != -1}")
    
    # Initialize DomBot
    print("\n2. Initializing DomBot...")
    try:
        dom_bot = DomBot()
        if not dom_bot.client:
            print("   [ERROR] OpenAI API key not configured")
            print("   Set OPENAI_API_KEY environment variable")
            return
        print("   [OK] DomBot initialized")
    except Exception as e:
        print(f"   [ERROR] Error initializing DomBot: {e}")
        return
    
    # Send a test request
    print("\n3. Sending test request...")
    test_message = "Hello, this is a test message. Please respond with a simple greeting."
    print(f"   Test message: {test_message}")
    
    try:
        response = await dom_bot.respond(
            user_text=test_message,
            channel_id="test_channel_123",
            user_id="test_user_456"
        )
        
        print("\n4. Response received:")
        print(f"   Message: {response.message}")
        print(f"   Actions: {len(response.actions)} action(s)")
        print(f"   Needs followup: {response.needs_followup}")
        
        # Check if response indicates an error
        if "error" in response.message.lower() or "fault" in response.message.lower():
            print(f"\n   [WARNING] Response message suggests an error occurred!")
            print(f"   This might indicate the request failed but was handled gracefully.")
        
        if response.actions:
            print("\n   Actions details:")
            for i, action in enumerate(response.actions, 1):
                print(f"      {i}. {action.tool_name}")
                print(f"         Args: {json.dumps(action.args, indent=10)}")
                print(f"         Result: {json.dumps(action.result, indent=10)}")
        
        # Check if this was a successful response
        if "error" not in response.message.lower() and "fault" not in response.message.lower():
            print("\n" + "=" * 60)
            print("[SUCCESS] Test completed successfully!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("[PARTIAL] Test completed but response indicates an error")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n   [ERROR] Error during request: {type(e).__name__}")
        print(f"   Error message: {str(e)}")
        
        # Try to extract more details from OpenAI errors
        error_details = {}
        error_body = None
        status_code = None
        
        if hasattr(e, 'response'):
            try:
                status_code = getattr(e.response, 'status_code', None)
                if hasattr(e.response, 'json'):
                    error_details = e.response.json()
                elif hasattr(e.response, 'text'):
                    error_body = e.response.text
            except Exception as ex:
                print(f"   [NOTE] Could not extract error details: {ex}")
        
        # Also check for OpenAI-specific error attributes
        if hasattr(e, 'body'):
            try:
                if isinstance(e.body, dict):
                    error_details.update(e.body)
                elif isinstance(e.body, str):
                    error_body = e.body
            except Exception:
                pass
        
        if status_code:
            print(f"   Status code: {status_code}")
        if error_details:
            print(f"   Error details: {json.dumps(error_details, indent=2)}")
        if error_body:
            print(f"   Error body: {error_body[:1000]}")
        
        # Check if response message indicates the error
        if 'response' in locals() and hasattr(response, 'message'):
            if "error" in response.message.lower() or "fault" in response.message.lower():
                print(f"\n   [NOTE] Response message indicates error: {response.message}")
        
        print("\n" + "=" * 60)
        print("[FAILED] Test failed!")
        print("=" * 60)
        
        # Don't raise - just show the error for debugging
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_dom_bot())

