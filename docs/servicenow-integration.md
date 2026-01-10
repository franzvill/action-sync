# ServiceNow Integration Guide

## Overview

The ServiceNow integration enables automatic creation and management of ServiceNow tickets based on events within the repository. This feature allows teams to seamlessly connect their development workflows with ServiceNow's IT Service Management (ITSM) capabilities.

## Features

### Ticket Management
- **Create Incidents**: Automatically create incidents with customizable urgency and impact levels
- **Create Change Requests**: Track deployments and changes through ServiceNow change management
- **Update Tickets**: Add work notes and update existing tickets
- **Search & Query**: Find incidents based on various criteria
- **Close Incidents**: Complete incidents with resolution notes

### Configuration
- Secure credential storage (username/password authentication)
- Connection testing to verify ServiceNow instance accessibility
- Support for custom ServiceNow instances

## Setup

### Prerequisites
- A ServiceNow instance (development, test, or production)
- ServiceNow user account with appropriate permissions:
  - `itil` role for incident management
  - `change_manager` role for change request creation (optional)

### Configuration Steps

1. **Access Settings**
   - Navigate to the Settings page in ActionSync
   - Locate the ServiceNow Configuration section

2. **Enter Credentials**
   - **Instance URL**: Your ServiceNow instance URL (e.g., `https://dev123456.service-now.com`)
   - **Username**: Your ServiceNow username
   - **Password**: Your ServiceNow password

3. **Test Connection**
   - Click "Test Connection" to verify your configuration
   - A successful test confirms that ActionSync can connect to your ServiceNow instance

4. **Save Configuration**
   - Click "Save" to store your configuration

## API Reference

### Endpoints

#### Get Configuration
```
GET /api/servicenow/config
```
Retrieve the current user's ServiceNow configuration.

**Response:**
```json
{
  "id": 1,
  "instance_url": "https://dev123456.service-now.com",
  "username": "admin",
  "created_at": "2024-01-10T10:00:00Z"
}
```

#### Create Configuration
```
POST /api/servicenow/config
```
Create ServiceNow configuration for the current user.

**Request Body:**
```json
{
  "instance_url": "https://dev123456.service-now.com",
  "username": "admin",
  "password": "your-password"
}
```

#### Update Configuration
```
PUT /api/servicenow/config
```
Update existing ServiceNow configuration.

**Request Body:**
```json
{
  "instance_url": "https://new-instance.service-now.com",
  "username": "new-username",
  "password": "new-password"
}
```

#### Delete Configuration
```
DELETE /api/servicenow/config
```
Remove ServiceNow configuration.

#### Test Connection
```
POST /api/servicenow/test
```
Test the ServiceNow connection with current configuration.

**Response:**
```json
{
  "success": true,
  "message": "Connection successful",
  "instance": "https://dev123456.service-now.com"
}
```

## ServiceNow Client Usage

The `ServiceNowClient` class provides methods for interacting with ServiceNow's REST API.

### Creating Incidents

```python
from servicenow_tools import ServiceNowClient

client = ServiceNowClient(
    instance_url="https://dev123456.service-now.com",
    username="admin",
    password="password"
)

# Create an incident
incident = await client.create_incident(
    short_description="Application error on production server",
    description="Detailed description of the issue...",
    urgency="1",  # 1=High, 2=Medium, 3=Low
    impact="2",   # 1=High, 2=Medium, 3=Low
    category="Software",
    subcategory="Application"
)

print(f"Created incident: {incident['number']}")
```

### Creating Change Requests

```python
# Create a change request
change = await client.create_change_request(
    short_description="Deploy new authentication system",
    description="Deploy version 2.0 of the authentication system",
    type_="normal",  # standard, normal, emergency
    risk="2",        # 1=High, 2=Medium, 3=Low, 4=Very Low
    impact="2"
)

print(f"Created change request: {change['number']}")
```

### Updating Tickets

```python
# Update an incident
updated = await client.update_incident(
    sys_id="abc123...",
    state="2",  # In Progress
    assigned_to="user.name"
)

# Add a work note
await client.add_work_note(
    table="incident",
    sys_id="abc123...",
    work_note="Investigated the issue and identified root cause"
)
```

### Searching Incidents

```python
# Search for incidents
incidents = await client.search_incidents(
    state="1",  # New
    assignment_group="IT Support",
    limit=10
)

for incident in incidents:
    print(f"{incident['number']}: {incident['short_description']}")
```

### Closing Incidents

```python
# Close an incident
closed = await client.close_incident(
    sys_id="abc123...",
    close_notes="Issue resolved by restarting the service",
    close_code="Solved (Permanently)"
)
```

## Use Cases

### 1. Automatic Incident Creation on Errors

Create incidents automatically when critical errors occur in your application:

```python
# Example: Monitor application logs and create incidents
if error_severity == "CRITICAL":
    incident = await servicenow_client.create_incident(
        short_description=f"Critical Error: {error_message}",
        description=f"Stack trace:\n{stack_trace}",
        urgency="1",
        impact="1",
        category="Software",
        assignment_group="DevOps Team"
    )
```

### 2. Deployment Tracking via Change Requests

Track deployments through ServiceNow change management:

```python
# Example: Create change request for deployment
change = await servicenow_client.create_change_request(
    short_description=f"Deploy {app_name} v{version}",
    description=f"Deploy changes:\n{changelog}",
    type_="normal",
    risk="2",
    impact="2",
    assignment_group="Release Management"
)
```

### 3. Meeting-Based Ticket Creation

Integrate with ActionSync's meeting processing to create ServiceNow tickets:

```python
# Example: Process meeting notes and create tickets
for action_item in meeting_action_items:
    if action_item.requires_incident:
        await servicenow_client.create_incident(
            short_description=action_item.summary,
            description=action_item.details,
            urgency=action_item.priority,
            impact=action_item.impact
        )
```

## Security Considerations

### Credential Storage
- Passwords are stored in the database
- In production, consider implementing encryption for sensitive fields
- Use environment variables for additional security layer

### API Authentication
- ServiceNow uses Basic Authentication (username/password)
- Consider using OAuth 2.0 for production environments
- Implement credential rotation policies

### Network Security
- Ensure HTTPS is used for all ServiceNow connections
- Configure firewall rules to allow outbound connections to ServiceNow
- Use VPN or private networking for enhanced security

## Troubleshooting

### Connection Issues

**Problem:** "Connection failed" error
**Solutions:**
- Verify instance URL is correct and accessible
- Check username and password are valid
- Ensure your ServiceNow instance is running
- Check firewall and network connectivity

### Authentication Failures

**Problem:** "HTTP 401 Unauthorized" error
**Solutions:**
- Verify credentials are correct
- Check user account has required roles
- Ensure account is not locked

### Permission Errors

**Problem:** "HTTP 403 Forbidden" error
**Solutions:**
- Verify user has `itil` role for incident management
- Check user has appropriate permissions for the operation
- Contact ServiceNow administrator for role assignments

## Best Practices

1. **Test in Development**: Always test integrations in a development instance first
2. **Error Handling**: Implement proper error handling for all ServiceNow API calls
3. **Rate Limiting**: Be mindful of ServiceNow API rate limits
4. **Logging**: Log all ticket creation and updates for audit purposes
5. **Monitoring**: Monitor integration health and ticket creation success rates

## Additional Resources

- [ServiceNow REST API Documentation](https://developer.servicenow.com/dev.do#!/reference/api/latest/rest/)
- [ServiceNow Table API](https://docs.servicenow.com/bundle/latest/page/integrate/inbound-rest/concept/c_TableAPI.html)
- [ActionSync API Documentation](/docs)
