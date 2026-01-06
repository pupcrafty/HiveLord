"""Configuration validation script - checks .env file setup."""
import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.config.settings import get_settings
from app.ingest.bluesky_client import BlueskyClient


def check_bluesky_config():
    """Check Bluesky configuration and provide helpful feedback."""
    print("=" * 60)
    print("Bluesky Configuration Check")
    print("=" * 60)
    
    settings = get_settings()
    client = BlueskyClient()
    
    # Check if Bluesky is enabled
    if not settings.enable_bluesky:
        print("[!] Bluesky is DISABLED (ENABLE_BLUESKY=False)")
        print("    Set ENABLE_BLUESKY=True in your .env file to enable it.")
        return False
    
    print("[OK] Bluesky is ENABLED")
    
    # Check required fields
    issues = []
    
    if not settings.bsky_handle:
        issues.append("BSKY_HANDLE is missing or empty")
        print("[X] BSKY_HANDLE: MISSING")
    else:
        print(f"[OK] BSKY_HANDLE: {settings.bsky_handle}")
    
    if not settings.bsky_app_password:
        issues.append("BSKY_APP_PASSWORD is missing or empty")
        print("[X] BSKY_APP_PASSWORD: MISSING")
    else:
        # Show first 4 chars and last 4 chars for verification
        pwd = settings.bsky_app_password
        masked = f"{pwd[:4]}...{pwd[-4:]}" if len(pwd) > 8 else "***"
        print(f"[OK] BSKY_APP_PASSWORD: {masked} (length: {len(pwd)})")
    
    # Check PDS host
    print(f"[OK] BSKY_PDS_HOST: {settings.bsky_pds_host}")
    
    if issues:
        print("\n" + "=" * 60)
        print("[ERROR] CONFIGURATION ISSUES FOUND:")
        for issue in issues:
            print(f"   - {issue}")
        print("\n" + "=" * 60)
        print("HOW TO FIX:")
        print("=" * 60)
        print("1. Open your .env file")
        print("2. Add the following variables:")
        print("")
        if not settings.bsky_handle:
            print("   BSKY_HANDLE=yourname.bsky.social")
        if not settings.bsky_app_password:
            print("   BSKY_APP_PASSWORD=your-app-password-here")
        print("")
        print("3. To create an app password:")
        print("   - Go to Bluesky Settings -> Privacy & Security -> App Passwords")
        print("   - Create a new app password")
        print("   - Copy it to your .env file (no quotes needed)")
        print("=" * 60)
        return False
    
    # Check if client thinks it's enabled
    if not client.is_enabled():
        print("\n[!] Client reports as not enabled (internal check failed)")
        return False
    
    print("\n" + "=" * 60)
    print("[OK] All required Bluesky configuration is present!")
    print("=" * 60)
    print("\nConfiguration Summary:")
    print(f"  Handle: {settings.bsky_handle}")
    print(f"  PDS Host: {settings.bsky_pds_host}")
    print(f"  App Password: {'[OK] Set' if settings.bsky_app_password else '[X] Missing'}")
    print("\nNote: This script only checks configuration presence.")
    print("      Run the main application to test authentication.")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = check_bluesky_config()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERROR] Error checking configuration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

