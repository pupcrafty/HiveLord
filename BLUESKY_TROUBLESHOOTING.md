# Bluesky Configuration Troubleshooting

## ✅ Configuration Check Results

Your `.env` file has all required Bluesky settings:
- `BSKY_HANDLE`: `pupcrafty` ✓
- `BSKY_APP_PASSWORD`: Set (19 characters) ✓
- `BSKY_PDS_HOST`: `https://bsky.social` ✓

## 🔍 Next Steps to Diagnose the Failure

Since your configuration is present, the issue is likely during authentication. The improved error handling will now show detailed error messages.

### 1. Run the Application Again

Run your main application and check the console output or database logs for detailed error messages. The error will now include:
- HTTP status code (e.g., 401, 403, 500)
- Error response from Bluesky API
- Specific error message

### 2. Common Issues and Solutions

#### Issue: HTTP 401 Unauthorized
**Cause**: Invalid credentials
**Solutions**:
- Verify your `BSKY_HANDLE` is correct (try `pupcrafty.bsky.social` if just `pupcrafty` doesn't work)
- Confirm you're using an **App Password**, not your regular account password
- Create a new app password:
  1. Go to Bluesky Settings → Privacy & Security → App Passwords
  2. Create a new app password
  3. Copy it immediately (you can't see it again)
  4. Update your `.env` file with the new password

#### Issue: HTTP 403 Forbidden
**Cause**: App password doesn't have required permissions
**Solution**: Create a new app password with full permissions

#### Issue: Connection/Network Error
**Cause**: Network issues or incorrect PDS host
**Solutions**:
- Check your internet connection
- Verify `BSKY_PDS_HOST` is `https://bsky.social`
- Try accessing `https://bsky.social` in your browser

#### Issue: Handle Format
**Note**: Bluesky accepts both formats:
- `pupcrafty` (short form)
- `pupcrafty.bsky.social` (full form)

If one doesn't work, try the other.

### 3. Verify App Password

To verify your app password is correct:
1. Go to Bluesky Settings → Privacy & Security → App Passwords
2. Check if your app password is listed
3. If you're unsure, delete the old one and create a new one
4. Update your `.env` file with the new password

### 4. Test Configuration

Run the configuration checker:
```bash
python check_config.py
```

This will verify all settings are present (but won't test authentication).

### 5. Check Error Logs

After running the application, check:
- Console output for detailed error messages
- Database events table (if database is enabled) for error logs
- Look for entries with `source="bluesky"` and `type="error"`

## 📝 Example .env Configuration

```env
# Bluesky Configuration
ENABLE_BLUESKY=True
BSKY_HANDLE=pupcrafty.bsky.social
BSKY_APP_PASSWORD=your-app-password-here
BSKY_PDS_HOST=https://bsky.social
```

**Important Notes**:
- No quotes needed around values in `.env` file
- App passwords are long strings (typically 19+ characters)
- Handle can be with or without `.bsky.social` suffix
- Make sure there are no extra spaces around the `=` sign

## 🔧 Quick Fix Checklist

- [ ] App password is from Bluesky Settings → App Passwords (not account password)
- [ ] App password is copied correctly (no extra spaces or characters)
- [ ] Handle is spelled correctly
- [ ] `.env` file is in the project root directory
- [ ] No quotes around values in `.env` file
- [ ] Restarted the application after changing `.env` file

## 📞 Still Having Issues?

If the error persists after checking the above:
1. Note the exact error message from the console/logs
2. Check the HTTP status code in the error
3. Verify the error response details (now included in improved error handling)

The improved error handling will show exactly what Bluesky's API is returning, which will help identify the specific issue.


