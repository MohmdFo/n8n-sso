# n8n SSO Cookie-Based Authentication

This document explains how the improved n8n SSO implementation works, similar to the Dify approach.

## How It Works

### 1. **Cookie Extraction Method (Preferred)**
When a user authenticates through Casdoor:
1. User is redirected to Casdoor for authentication
2. After successful authentication, they're redirected back to our callback
3. We extract user info from the JWT token
4. We create/update the user in n8n database
5. **We login to n8n via REST API to get the `n8n-auth` cookie**
6. **We set the `n8n-auth` cookie on our response**
7. **We redirect directly to `http://107.189.19.66:8510/home/workflows`**

### 2. **Form Submission Fallback**
If cookie extraction fails, we fall back to the current HTML form submission method.

## Key Improvements

### ✅ **Seamless User Experience**
- Direct redirect to n8n workflows page
- No manual form submission
- No loading screens (if cookie method works)

### ✅ **Proper Session Management**
- Uses n8n's native authentication cookies
- Follows n8n's security practices
- Proper cookie domain and security settings

### ✅ **Similar to Dify Implementation**
- Same approach as your working Dify SSO
- Direct cookie setting and redirect
- Fallback mechanism for reliability

## Code Changes Made

### 1. **Enhanced Cookie Extraction**
```python
def extract_n8n_auth_cookie(response) -> str | None:
    """Extract n8n-auth cookie from httpx Response."""
    # Check cookies attribute and set-cookie headers
    # Returns the cookie value or None
```

### 2. **Dual-Method Authentication**
```python
# Method 1: Direct cookie setting (preferred)
if auth_cookie:
    response = RedirectResponse(url=n8n_workflows_url, status_code=302)
    response.set_cookie(
        key="n8n-auth",
        value=auth_cookie,
        domain=cookie_domain,
        path="/",
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=7 * 24 * 3600  # 7 days (n8n default)
    )
    return response

# Method 2: Fallback to form submission
else:
    # HTML form auto-submit (current method)
```

### 3. **Enhanced Logging**
- Detailed logging for debugging
- Cookie extraction status
- Response headers inspection
- Authentication flow tracking

## Configuration

### Required Environment Variables
```bash
# n8n Configuration
N8N_BASE_URL=http://107.189.19.66:8510
N8N_DB_DSN=postgresql+asyncpg://user:password@host:5432/n8n

# n8n Owner Credentials (for testing)
N8N_OWNER_EMAIL=owner@example.com  
N8N_OWNER_PASSWORD=your-n8n-owner-password

# Security
COOKIE_SECURE=false  # Set to true for HTTPS
```

## Testing

Run the test script to validate the implementation:

```bash
python apps/tests/test_sso_flow.py
```

This will:
1. Test n8n login and cookie extraction
2. Validate the extracted cookie
3. Confirm the cookie works for authenticated requests

## Expected Flow

### Successful Authentication:
1. User clicks SSO login
2. Redirects to Casdoor
3. User authenticates 
4. Returns to our callback
5. **Extracts n8n-auth cookie**
6. **Sets cookie and redirects to `/home/workflows`**
7. **User sees n8n workflows page, fully logged in**

### Fallback (if cookie extraction fails):
1. Same steps 1-4
2. Cookie extraction fails
3. **Falls back to HTML form submission**
4. User briefly sees loading screen
5. Gets logged in via form POST

## Benefits Over Current Implementation

1. **No form submission delays** (when cookie method works)
2. **Direct redirect to workflows page**
3. **Proper browser session handling**
4. **More secure** (no credentials in HTML)
5. **Follows n8n's native auth pattern**
6. **Better user experience** (seamless redirect)

## Cookie Security

The implementation properly handles:
- **Domain matching** (sets cookie for n8n domain)
- **Security flags** (httpOnly, secure, sameSite)
- **Expiration** (matches n8n's 7-day default)
- **Path restriction** (cookie applies to all n8n routes)

## Debugging

If issues occur, check the logs for:
- Cookie extraction success/failure
- n8n login response headers
- Cookie validation attempts
- Fallback method activation

The logs will show exactly what's happening in each step of the authentication flow.
