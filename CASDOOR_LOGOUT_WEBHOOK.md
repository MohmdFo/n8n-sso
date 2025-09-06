# Casdoor Logout Webhook Integration

This document explains how to set up logout synchronization between Casdoor and n8n using webhooks.

## How It Works

When a user logs out from Casdoor, it automatically logs them out from n8n as well, ensuring consistent authentication state across both systems.

### Flow:
1. **User logs out from Casdoor**
2. **Casdoor sends webhook** to your SSO gateway
3. **Gateway receives webhook** and identifies the user
4. **Gateway calls n8n logout API** to invalidate the user's session
5. **User is logged out from both systems**

## Setup Instructions

### 1. Configure Casdoor Webhook

In your Casdoor admin panel:

1. Go to **Webhooks** section
2. Click **"Add Webhook"**
3. Fill in the webhook details:

```
Name: n8n-logout-sync
Organization: organization_sharif
Address: http://107.189.19.66:8512/v1/auth/casdoor/webhook
Method: POST
Content Type: application/json
Events: logout
Extended User: ✅ Enable
User Fields: Name, Email, FirstName, DisplayName, LastName
Active: ✅ Enable
```

### 2. Production Configuration

For production deployment, update the webhook URL to use your production domain:

```
Address: https://your-production-domain.com/auth/casdoor/webhook
```

### 3. Test the Integration

#### Automatic Testing:
```bash
python3 test_logout_webhook.py
```

#### Manual Testing:
1. Login via SSO: `http://107.189.19.66:8512/auth/casdoor/login`
2. Verify you're logged into n8n
3. Logout from Casdoor directly
4. Check that you're also logged out from n8n

#### Manual Logout Endpoint:
You can also test manual logout:
```
GET http://107.189.19.66:8512/auth/casdoor/logout
```

## API Endpoints

### Webhook Endpoint
```
POST /auth/casdoor/webhook
Content-Type: application/json
```

Receives logout events from Casdoor and processes them.

**Expected Payload:**
```json
{
  "id": 9078,
  "action": "logout",
  "user": "admin",
  "organization": "organization_sharif",
  "extendedUser": {
    "name": "admin",
    "email": "admin@ai-lab.ir",
    "displayName": "Admin User"
  }
}
```

**Response:**
```json
{
  "success": true,
  "webhook_id": 9078,
  "result": {
    "status": "success",
    "user_email": "admin@ai-lab.ir",
    "n8n_logout_status": 200,
    "message": "User logged out from n8n"
  }
}
```

### Manual Logout Endpoint
```
GET /auth/casdoor/logout
```

Manually logs user out from n8n and redirects to Casdoor logout page.

## Troubleshooting

### Check Webhook Delivery

1. **Casdoor Logs**: Check if webhooks are being sent
2. **Gateway Logs**: Check if webhooks are being received
3. **n8n Logs**: Check if logout requests are successful

### Common Issues

1. **Webhook URL not reachable**
   - Ensure the SSO gateway is accessible from Casdoor
   - Check firewall settings

2. **Wrong user email**
   - Verify `extendedUser.email` matches n8n user email
   - Check user mapping in logs

3. **n8n logout fails**
   - Check n8n API accessibility
   - Verify n8n logout endpoint is working

### Logs to Monitor

```bash
# Check webhook reception
docker logs n8n-sso-gateway | grep "webhook"

# Check logout processing  
docker logs n8n-sso-gateway | grep "logout"

# Check n8n API calls
docker logs n8n-sso-gateway | grep "n8n_client"
```

## Security Considerations

1. **Webhook Security**: Consider adding webhook signature verification
2. **Network Security**: Use HTTPS in production
3. **Rate Limiting**: Consider adding rate limiting to webhook endpoint
4. **Error Handling**: Logs sensitive errors without exposing details

## Environment Variables

Production configuration (`.env-prod`):

```bash
# n8n Configuration (Production)
N8N_BASE_URL=https://n8n.ai-lab.ir
N8N_DB_DSN=postgresql+asyncpg://n8nio_user:PASSWORD@172.15.40.12:31926/n8nio2
N8N_OWNER_EMAIL=admin@ai-lab.ir
N8N_OWNER_PASSWORD=ADMIN_PASSWORD

# Casdoor Configuration
CASDOOR_ENDPOINT=https://iam.ai-lab.ir
CASDOOR_CLIENT_ID=your_client_id
CASDOOR_CLIENT_SECRET=your_client_secret
CASDOOR_ORG_NAME=organization_sharif
CASDOOR_APP_NAME=application_panel

# Security
DEBUG=false
SECRET_KEY=your-production-secret-key
```

**Note**: Replace placeholder values with your actual credentials before deployment.
