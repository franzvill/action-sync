"""
ServiceNow Tools

Client for interacting with ServiceNow REST API.
Supports creating and managing incidents, change requests, and other ticket types.
"""

import httpx
from typing import Any, Optional, Dict, List


class ServiceNowClient:
    """Async client for ServiceNow REST API."""

    def __init__(self, instance_url: str, username: str, password: str):
        """
        Initialize ServiceNow client.
        
        Args:
            instance_url: ServiceNow instance URL (e.g., https://dev123456.service-now.com)
            username: ServiceNow username
            password: ServiceNow password
        """
        self.instance_url = instance_url.rstrip("/")
        self.auth = (username, password)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an authenticated request to ServiceNow API.
        
        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to httpx.request
            
        Returns:
            Response data as dictionary
            
        Raises:
            Exception: If request fails
        """
        url = f"{self.instance_url}/api/now{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=30.0,
                **kwargs
            )
            if not response.is_success:
                error_detail = ""
                try:
                    error_body = response.json()
                    error = error_body.get("error", {})
                    message = error.get("message", "")
                    detail = error.get("detail", "")
                    if message:
                        error_detail = f" Message: {message}"
                    if detail:
                        error_detail += f" Detail: {detail}"
                except:
                    error_detail = response.text[:500] if response.text else ""
                raise Exception(f"ServiceNow API error: HTTP {response.status_code}{error_detail}")
            if response.status_code == 204:
                return {"success": True}
            return response.json()

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the ServiceNow connection.
        
        Returns:
            Connection status and user information
        """
        try:
            # Try to get current user info as a connection test
            data = await self._request("GET", "/table/sys_user", params={"sysparm_limit": 1})
            return {
                "success": True,
                "message": "Connection successful",
                "instance": self.instance_url
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }

    async def create_incident(
        self,
        short_description: str,
        description: Optional[str] = None,
        urgency: str = "3",  # 1=High, 2=Medium, 3=Low
        impact: str = "3",   # 1=High, 2=Medium, 3=Low
        assignment_group: Optional[str] = None,
        assigned_to: Optional[str] = None,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        **additional_fields
    ) -> Dict[str, Any]:
        """
        Create a new incident in ServiceNow.
        
        Args:
            short_description: Brief description of the incident
            description: Detailed description
            urgency: Urgency level (1=High, 2=Medium, 3=Low)
            impact: Impact level (1=High, 2=Medium, 3=Low)
            assignment_group: Assignment group name or sys_id
            assigned_to: Assigned user name or sys_id
            category: Incident category
            subcategory: Incident subcategory
            **additional_fields: Any additional fields to set
            
        Returns:
            Created incident details
        """
        data = {
            "short_description": short_description,
            "urgency": urgency,
            "impact": impact,
        }
        
        if description:
            data["description"] = description
        if assignment_group:
            data["assignment_group"] = assignment_group
        if assigned_to:
            data["assigned_to"] = assigned_to
        if category:
            data["category"] = category
        if subcategory:
            data["subcategory"] = subcategory
            
        # Add any additional fields
        data.update(additional_fields)
        
        response = await self._request("POST", "/table/incident", json=data)
        return response.get("result", {})

    async def get_incident(self, sys_id: str) -> Dict[str, Any]:
        """
        Get an incident by sys_id.
        
        Args:
            sys_id: ServiceNow sys_id of the incident
            
        Returns:
            Incident details
        """
        response = await self._request("GET", f"/table/incident/{sys_id}")
        return response.get("result", {})

    async def update_incident(self, sys_id: str, **fields) -> Dict[str, Any]:
        """
        Update an incident.
        
        Args:
            sys_id: ServiceNow sys_id of the incident
            **fields: Fields to update
            
        Returns:
            Updated incident details
        """
        response = await self._request("PATCH", f"/table/incident/{sys_id}", json=fields)
        return response.get("result", {})

    async def search_incidents(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        assignment_group: Optional[str] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search for incidents.
        
        Args:
            query: Encoded query string (ServiceNow syntax)
            state: Incident state
            assignment_group: Filter by assignment group
            assigned_to: Filter by assigned user
            limit: Maximum number of results
            
        Returns:
            List of matching incidents
        """
        params = {"sysparm_limit": limit}
        
        query_parts = []
        if query:
            query_parts.append(query)
        if state:
            query_parts.append(f"state={state}")
        if assignment_group:
            query_parts.append(f"assignment_group={assignment_group}")
        if assigned_to:
            query_parts.append(f"assigned_to={assigned_to}")
            
        if query_parts:
            params["sysparm_query"] = "^".join(query_parts)
            
        response = await self._request("GET", "/table/incident", params=params)
        return response.get("result", [])

    async def create_change_request(
        self,
        short_description: str,
        description: Optional[str] = None,
        type_: str = "normal",  # standard, normal, emergency
        risk: str = "3",  # 1=High, 2=Medium, 3=Low, 4=Very Low
        impact: str = "3",
        assignment_group: Optional[str] = None,
        assigned_to: Optional[str] = None,
        **additional_fields
    ) -> Dict[str, Any]:
        """
        Create a new change request in ServiceNow.
        
        Args:
            short_description: Brief description of the change
            description: Detailed description
            type_: Change type (standard, normal, emergency)
            risk: Risk level (1=High, 2=Medium, 3=Low, 4=Very Low)
            impact: Impact level (1=High, 2=Medium, 3=Low)
            assignment_group: Assignment group name or sys_id
            assigned_to: Assigned user name or sys_id
            **additional_fields: Any additional fields to set
            
        Returns:
            Created change request details
        """
        data = {
            "short_description": short_description,
            "type": type_,
            "risk": risk,
            "impact": impact,
        }
        
        if description:
            data["description"] = description
        if assignment_group:
            data["assignment_group"] = assignment_group
        if assigned_to:
            data["assigned_to"] = assigned_to
            
        # Add any additional fields
        data.update(additional_fields)
        
        response = await self._request("POST", "/table/change_request", json=data)
        return response.get("result", {})

    async def get_change_request(self, sys_id: str) -> Dict[str, Any]:
        """
        Get a change request by sys_id.
        
        Args:
            sys_id: ServiceNow sys_id of the change request
            
        Returns:
            Change request details
        """
        response = await self._request("GET", f"/table/change_request/{sys_id}")
        return response.get("result", {})

    async def add_work_note(self, table: str, sys_id: str, work_note: str) -> Dict[str, Any]:
        """
        Add a work note to a ticket.
        
        Args:
            table: Table name (e.g., 'incident', 'change_request')
            sys_id: ServiceNow sys_id of the ticket
            work_note: Work note text
            
        Returns:
            Updated ticket details
        """
        response = await self._request(
            "PATCH",
            f"/table/{table}/{sys_id}",
            json={"work_notes": work_note}
        )
        return response.get("result", {})

    async def close_incident(self, sys_id: str, close_notes: str, close_code: str = "Solved (Permanently)") -> Dict[str, Any]:
        """
        Close an incident.
        
        Args:
            sys_id: ServiceNow sys_id of the incident
            close_notes: Notes about the resolution
            close_code: Close code/resolution
            
        Returns:
            Updated incident details
        """
        response = await self._request(
            "PATCH",
            f"/table/incident/{sys_id}",
            json={
                "state": "7",  # Closed
                "close_notes": close_notes,
                "close_code": close_code
            }
        )
        return response.get("result", {})
