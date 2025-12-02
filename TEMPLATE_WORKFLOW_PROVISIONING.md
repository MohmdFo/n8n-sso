# Template Workflow Automatic Provisioning

## Overview

This feature automatically creates template workflows for new users when they register for the first time in the n8n SSO Gateway. The system provides users with pre-configured workflows that they can customize according to their needs.

## How It Works

### 1. **User Registration Flow**
When a user registers for the first time through Casdoor SSO:

1. User authenticates via Casdoor OAuth
2. System creates user account and personal project in n8n database
3. **NEW:** System automatically creates template workflow(s) for the user
4. User is redirected to n8n with their new template workflow ready

### 2. **Template Workflow Processing**
The template workflow (Google Calendar & Telegram) is automatically:

- **Cleaned**: Removes user-specific credentials and webhook IDs
- **Personalized**: Updates name to indicate it's a template
- **Secured**: Removes existing credential references to require new setup
- **Deactivated**: Set as inactive so user can configure before use

### 3. **Database Integration**
The workflow is properly integrated into n8n's database:

- Inserted into the `workflow` table with proper metadata
- Associated with user's personal project via `workflow_entity_relation`
- Linked directly to user for ownership via `workflow_entity_relation`

## Technical Implementation

### Core Components

#### 1. **Template Manager** (`apps/integrations/template_manager.py`)
```python
class TemplateManager:
    - Discovers available workflow templates
    - Manages template loading and preparation
    - Provides default template selection
```

#### 2. **Database Operations** (`apps/integrations/n8n_db.py`)
```python
async def create_template_workflow_for_user():
    - Creates workflow in n8n database
    - Sets up proper project and user associations
    - Handles error scenarios gracefully
```

#### 3. **Enhanced User Registration** (`apps/integrations/n8n_db.py`)
```python
async def ensure_user_project_binding():
    - Detects new user registration
    - Automatically triggers template workflow creation
    - Logs success/failure for monitoring
```

### Template Preparation Process

When preparing a template for a user, the system:

1. **Removes Credentials**: Clears all credential references to require new setup
2. **Clears Webhooks**: Removes webhook IDs to generate fresh ones
3. **Resets Calendar Config**: Clears calendar references for user configuration
4. **Updates Metadata**: Marks as template and not credential-ready
5. **Deactivates Workflow**: Sets `active: false` for user review
6. **Updates Name**: Appends "(Template)" to workflow name

## Template Structure

### Available Templates

Currently includes:
- **02-Google-Calendar&Telegram.json**: AI-powered calendar management via Telegram

### Adding New Templates

To add new templates:

1. Place `.json` workflow file in `apps/templates/` directory
2. Template Manager automatically discovers it
3. No code changes required

Template files should follow n8n's standard workflow export format.

## Configuration

### Default Template Selection

The system automatically selects the default template using this priority:

1. **Primary**: `02-Google-Calendar&Telegram` (if available)
2. **Fallback**: First available template in templates directory
3. **None**: Gracefully handles missing templates

### Template Directory

Templates are stored in: `apps/templates/`

Current template:
- `02-Google-Calendar&Telegram.json` - Google Calendar & Telegram integration

## User Experience

### For New Users

1. **Register**: Complete Casdoor SSO authentication
2. **Auto-Setup**: Template workflow automatically created
3. **Access**: Log into n8n and find pre-configured template
4. **Configure**: Set up credentials and activate workflow
5. **Use**: Enjoy AI-powered calendar management

### Template Workflow Features

The Google Calendar & Telegram template provides:

- **Telegram Bot Integration**: Receive calendar commands via Telegram
- **Google Calendar Management**: Create, update, and manage calendar events
- **AI Processing**: Natural language processing for calendar operations
- **Voice Support**: Voice message processing capabilities

## Security Considerations

### Template Sanitization

Templates are automatically sanitized for security:

- **No Credentials**: All authentication removed
- **No User Data**: Personal information stripped
- **No Active Webhooks**: Webhook URLs regenerated
- **Read-Only State**: Templates start inactive

### Database Security

- **Proper Relations**: Workflows correctly associated with users/projects
- **Transaction Safety**: All operations wrapped in database transactions
- **Error Handling**: Graceful failure with detailed logging

## Monitoring & Logging

### Success Indicators

```json
{
  "message": "Template workflow created for user",
  "user_id": "uuid",
  "project_id": "string",
  "workflow_id": "string", 
  "workflow_name": "string",
  "template_name": "string"
}
```

### Failure Indicators

```json
{
  "message": "Failed to create template workflow for user",
  "user_id": "uuid",
  "project_id": "string", 
  "user_email": "string",
  "error": "string"
}
```

### Health Monitoring

Monitor these metrics:
- Template workflow creation success rate
- Template loading failures
- Database insertion errors
- User registration completion rates

## Error Handling

### Graceful Degradation

If template creation fails:

1. **User Registration**: Continues normally
2. **Access Granted**: User can still access n8n
3. **Manual Setup**: User can manually create workflows
4. **Logging**: Error details captured for investigation

### Common Issues

- **Missing Template**: Template file not found or corrupted
- **Database Errors**: Connection or constraint violations  
- **Permission Issues**: File system access problems
- **JSON Errors**: Malformed template data

All issues are logged with context for debugging.

## Testing

### Test Coverage

Comprehensive tests verify:

- Template discovery and loading
- User data sanitization
- Database workflow creation
- Error handling scenarios
- End-to-end integration

### Test Execution

```bash
# Run template-specific tests
python test_template_workflow.py

# Run full test suite
python apps/tests/run_all_tests.py
```

## Future Enhancements

### Planned Features

1. **Multiple Templates**: Allow users to choose from multiple templates
2. **Custom Templates**: Enable organizations to add custom templates
3. **Template Marketplace**: Community-shared workflow templates
4. **Version Management**: Template versioning and updates
5. **Analytics**: Track template usage and effectiveness

### Extension Points

- Template metadata and categorization
- User preference-based template selection
- Dynamic template customization
- Template sharing and collaboration

## Conclusion

The template workflow system provides new users with immediate value by automatically provisioning useful, pre-configured workflows. This reduces time-to-value and improves user onboarding experience while maintaining security and flexibility.

Users get:
✅ **Instant Value**: Pre-configured workflows ready to use  
✅ **Easy Onboarding**: No need to build workflows from scratch  
✅ **Secure Setup**: Credentials and personal data properly isolated  
✅ **Customization**: Full ability to modify and extend templates  

The system handles the complexity automatically while providing robust error handling and monitoring capabilities.