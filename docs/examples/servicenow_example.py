"""
Example: Using ServiceNow Integration

This example demonstrates how to use the ServiceNow integration
to create incidents and change requests programmatically.

Prerequisites:
1. Configure ServiceNow in ActionSync settings
2. Have valid ServiceNow credentials
"""

import asyncio
from servicenow_tools import ServiceNowClient


async def main():
    # Initialize ServiceNow client
    # In production, these would come from the database configuration
    client = ServiceNowClient(
        instance_url="https://dev123456.service-now.com",
        username="your-username",
        password="your-password"
    )

    print("ServiceNow Integration Examples\n")
    print("=" * 50)

    # Example 1: Test connection
    print("\n1. Testing connection...")
    result = await client.test_connection()
    if result["success"]:
        print(f"   ✓ Connected to {result['instance']}")
    else:
        print(f"   ✗ Connection failed: {result['message']}")
        return

    # Example 2: Create an incident
    print("\n2. Creating an incident...")
    try:
        incident = await client.create_incident(
            short_description="Application error on production server",
            description="""
Production server experiencing intermittent errors.
Error: Connection timeout to database
Affected users: ~50
Impact: High priority customers cannot access dashboard
            """.strip(),
            urgency="1",  # High
            impact="1",   # High
            category="Software",
            subcategory="Application"
        )
        print(f"   ✓ Created incident: {incident.get('number', 'N/A')}")
        print(f"   Sys ID: {incident.get('sys_id', 'N/A')}")
    except Exception as e:
        print(f"   ✗ Failed to create incident: {e}")

    # Example 3: Create a change request
    print("\n3. Creating a change request...")
    try:
        change = await client.create_change_request(
            short_description="Deploy authentication system v2.0",
            description="""
Deployment of new authentication system with features:
- Multi-factor authentication
- OAuth 2.0 support
- Improved password policies
- Session management enhancements

Deployment window: Saturday 2 AM - 4 AM
Rollback plan: Revert to v1.9 if issues occur
            """.strip(),
            type_="normal",
            risk="2",     # Medium
            impact="2"    # Medium
        )
        print(f"   ✓ Created change request: {change.get('number', 'N/A')}")
        print(f"   Sys ID: {change.get('sys_id', 'N/A')}")
    except Exception as e:
        print(f"   ✗ Failed to create change request: {e}")

    # Example 4: Search for incidents
    print("\n4. Searching for incidents...")
    try:
        incidents = await client.search_incidents(
            state="1",  # New
            limit=5
        )
        print(f"   Found {len(incidents)} new incident(s)")
        for inc in incidents[:3]:  # Show first 3
            print(f"   - {inc.get('number', 'N/A')}: {inc.get('short_description', 'N/A')[:50]}...")
    except Exception as e:
        print(f"   ✗ Failed to search incidents: {e}")

    print("\n" + "=" * 50)
    print("\nFor more examples, see: docs/servicenow-integration.md")


if __name__ == "__main__":
    print("Note: This example requires a valid ServiceNow instance and credentials.")
    print("Update the credentials in the script before running.\n")
    
    # Uncomment to run the examples:
    # asyncio.run(main())
    
    print("Example script ready. Review the code to understand the usage.")
