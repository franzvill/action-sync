"""
Jira Tools for Claude SDK

Custom tools for interacting with Jira REST API v3.
"""

import re
import httpx
from typing import Any, Optional, List
from claude_agent_sdk import tool, create_sdk_mcp_server


def markdown_to_adf(text: str) -> dict:
    """
    Convert markdown-like text to Atlassian Document Format (ADF).
    Supports headers, bullet lists, numbered lists, code blocks, and paragraphs.
    """
    lines = text.split('\n')
    content = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Code block (```)
        if line.strip().startswith('```'):
            code_lines = []
            language = line.strip()[3:].strip() or None
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # Skip closing ```
            code_block = {
                "type": "codeBlock",
                "content": [{"type": "text", "text": '\n'.join(code_lines)}]
            }
            if language:
                code_block["attrs"] = {"language": language}
            content.append(code_block)
            continue

        # Headers (## Header or **Header**)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            content.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": [{"type": "text", "text": header_text}]
            })
            i += 1
            continue

        # Bullet list items
        if re.match(r'^[\s]*[-*]\s+', line):
            list_items = []
            while i < len(lines) and re.match(r'^[\s]*[-*]\s+', lines[i]):
                item_text = re.sub(r'^[\s]*[-*]\s+', '', lines[i])
                list_items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": parse_inline_formatting(item_text)
                    }]
                })
                i += 1
            content.append({
                "type": "bulletList",
                "content": list_items
            })
            continue

        # Numbered list items
        if re.match(r'^[\s]*\d+[.)]\s+', line):
            list_items = []
            while i < len(lines) and re.match(r'^[\s]*\d+[.)]\s+', lines[i]):
                item_text = re.sub(r'^[\s]*\d+[.)]\s+', '', lines[i])
                list_items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": parse_inline_formatting(item_text)
                    }]
                })
                i += 1
            content.append({
                "type": "orderedList",
                "content": list_items
            })
            continue

        # Regular paragraph
        content.append({
            "type": "paragraph",
            "content": parse_inline_formatting(line)
        })
        i += 1

    # Ensure we have at least one paragraph
    if not content:
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": text}]
        })

    return {
        "type": "doc",
        "version": 1,
        "content": content
    }


def parse_inline_formatting(text: str) -> List[dict]:
    """Parse inline formatting like **bold**, *italic*, `code`."""
    result = []
    current_pos = 0

    # Pattern for inline code, bold, italic
    pattern = r'(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)'

    for match in re.finditer(pattern, text):
        # Add text before match
        if match.start() > current_pos:
            result.append({"type": "text", "text": text[current_pos:match.start()]})

        matched = match.group(0)
        if matched.startswith('`') and matched.endswith('`'):
            # Inline code
            result.append({
                "type": "text",
                "text": matched[1:-1],
                "marks": [{"type": "code"}]
            })
        elif matched.startswith('**') and matched.endswith('**'):
            # Bold
            result.append({
                "type": "text",
                "text": matched[2:-2],
                "marks": [{"type": "strong"}]
            })
        elif matched.startswith('*') and matched.endswith('*'):
            # Italic
            result.append({
                "type": "text",
                "text": matched[1:-1],
                "marks": [{"type": "em"}]
            })

        current_pos = match.end()

    # Add remaining text
    if current_pos < len(text):
        result.append({"type": "text", "text": text[current_pos:]})

    # If no formatting found, just return plain text
    if not result:
        result.append({"type": "text", "text": text})

    return result


class JiraClient:
    """Async client for Jira REST API v3."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to Jira API."""
        url = f"{self.base_url}/rest/api/3{endpoint}"
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
                    errors = error_body.get("errors", {})
                    error_messages = error_body.get("errorMessages", [])
                    if errors:
                        error_detail = f" Errors: {errors}"
                    if error_messages:
                        error_detail = f" Messages: {error_messages}"
                except:
                    error_detail = response.text[:500] if response.text else ""
                raise Exception(f"HTTP {response.status_code}{error_detail}")
            if response.status_code == 204:
                return {"success": True}
            return response.json()

    async def search_issues(self, jql: str, max_results: int = 50, fields: Optional[list] = None) -> dict:
        """Search for issues using JQL."""
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields or ["summary", "status", "issuetype", "priority", "assignee", "description"]
        }
        return await self._request("POST", "/search/jql", json=body)

    async def get_issue(self, issue_key: str) -> dict:
        """Get a single issue by key."""
        return await self._request("GET", f"/issue/{issue_key}")

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        labels: Optional[list] = None,
        priority: Optional[str] = None
    ) -> dict:
        """Create a new issue."""
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type}
        }

        if description:
            fields["description"] = markdown_to_adf(description)

        if labels and isinstance(labels, list) and len(labels) > 0:
            # Ensure all labels are strings
            fields["labels"] = [str(l) for l in labels if l]

        if priority:
            fields["priority"] = {"name": priority}

        return await self._request("POST", "/issue", json={"fields": fields})

    async def update_issue(self, issue_key: str, fields: dict) -> dict:
        """Update an existing issue."""
        update_fields = {}

        if "summary" in fields:
            update_fields["summary"] = fields["summary"]

        if "description" in fields:
            update_fields["description"] = markdown_to_adf(fields["description"])

        if "labels" in fields:
            update_fields["labels"] = fields["labels"]

        if "priority" in fields:
            update_fields["priority"] = {"name": fields["priority"]}

        return await self._request("PUT", f"/issue/{issue_key}", json={"fields": update_fields})

    async def add_comment(self, issue_key: str, comment: str) -> dict:
        """Add a comment to an issue."""
        body = {
            "body": markdown_to_adf(comment)
        }
        return await self._request("POST", f"/issue/{issue_key}/comment", json=body)

    async def get_project(self, project_key: str) -> dict:
        """Get project details."""
        return await self._request("GET", f"/project/{project_key}")

    async def get_issue_types(self, project_key: str) -> dict:
        """Get available issue types for a project."""
        return await self._request("GET", f"/issue/createmeta/{project_key}/issuetypes")

    async def transition_issue(self, issue_key: str, transition_name: str) -> dict:
        """Transition an issue to a new status."""
        # First get available transitions
        transitions = await self._request("GET", f"/issue/{issue_key}/transitions")

        # Find the transition by name
        transition_id = None
        for t in transitions.get("transitions", []):
            if t["name"].lower() == transition_name.lower():
                transition_id = t["id"]
                break

        if not transition_id:
            available = [t["name"] for t in transitions.get("transitions", [])]
            return {"error": f"Transition '{transition_name}' not found. Available: {available}"}

        return await self._request(
            "POST",
            f"/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}}
        )


# Global client instance (set before creating tools)
_jira_client: Optional[JiraClient] = None
_result_callback: Optional[Any] = None
_meeting_search_fn: Optional[Any] = None


def set_jira_client(client: JiraClient):
    """Set the global Jira client instance."""
    global _jira_client
    _jira_client = client


def set_result_callback(callback):
    """Set a callback to be called with tool results."""
    global _result_callback
    _result_callback = callback


def set_meeting_search_fn(fn):
    """Set the meeting search function for semantic search."""
    global _meeting_search_fn
    _meeting_search_fn = fn


def get_jira_client() -> JiraClient:
    """Get the global Jira client instance."""
    if _jira_client is None:
        raise RuntimeError("Jira client not initialized. Call set_jira_client first.")
    return _jira_client


async def _send_result(result: dict):
    """Send tool result via callback if set."""
    if _result_callback:
        text = ""
        for item in result.get("content", []):
            if item.get("type") == "text":
                text += item.get("text", "")
        if text:
            await _result_callback({"type": "tool_result", "content": text})


# Tool definitions

@tool(
    "search",
    "Search for Jira issues using JQL (Jira Query Language). Returns matching issues with their key, summary, status, and other fields.",
    {
        "jql": str,
        "max_results": int
    }
)
async def jira_search(args: dict) -> dict:
    """Search Jira issues using JQL."""
    client = get_jira_client()
    jql = args["jql"]
    max_results = args.get("max_results", 20)

    try:
        result = await client.search_issues(jql, max_results)
        issues = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            issues.append({
                "key": issue["key"],
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "type": fields.get("issuetype", {}).get("name"),
                "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
                "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None
            })

        res = {
            "content": [
                {"type": "text", "text": f"Found {len(issues)} issues:\n" + "\n".join(
                    f"- {i['key']}: {i['summary']} [{i['status']}]" for i in issues
                )}
            ]
        }
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error searching issues: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "get_issue",
    "Get details of a specific Jira issue by its key (e.g., PROJ-123).",
    {"issue_key": str}
)
async def jira_get_issue(args: dict) -> dict:
    """Get a Jira issue by key."""
    client = get_jira_client()
    issue_key = args["issue_key"]

    try:
        issue = await client.get_issue(issue_key)
        fields = issue.get("fields", {})

        # Extract description text
        desc = fields.get("description")
        desc_text = ""
        if desc and desc.get("content"):
            for block in desc["content"]:
                if block.get("type") == "paragraph":
                    for content in block.get("content", []):
                        if content.get("type") == "text":
                            desc_text += content.get("text", "")

        result = f"""Issue: {issue['key']}
Summary: {fields.get('summary')}
Type: {fields.get('issuetype', {}).get('name')}
Status: {fields.get('status', {}).get('name')}
Priority: {fields.get('priority', {}).get('name') if fields.get('priority') else 'None'}
Assignee: {fields.get('assignee', {}).get('displayName') if fields.get('assignee') else 'Unassigned'}
Description: {desc_text or 'No description'}"""

        res = {"content": [{"type": "text", "text": result}]}
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error getting issue: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "create_issue",
    "Create a new Jira issue. Requires project key, summary, and optionally issue type, description, labels, and priority. IMPORTANT: First call get_project_issue_types to see valid issue types for the project.",
    {
        "project_key": str,
        "summary": str,
        "issue_type": str,
        "description": str,
        "labels": list,
        "priority": str
    }
)
async def jira_create_issue(args: dict) -> dict:
    """Create a new Jira issue."""
    client = get_jira_client()
    issue_type = args.get("issue_type", "Task")

    try:
        result = await client.create_issue(
            project_key=args["project_key"],
            summary=args["summary"],
            issue_type=issue_type,
            description=args.get("description"),
            labels=args.get("labels"),
            priority=args.get("priority")
        )

        res = {
            "content": [
                {"type": "text", "text": f"Created issue {result['key']}: {args['summary']}"}
            ]
        }
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error creating issue: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "update_issue",
    "Update an existing Jira issue. Can update summary, description, labels, or priority.",
    {
        "issue_key": str,
        "summary": str,
        "description": str,
        "labels": list,
        "priority": str
    }
)
async def jira_update_issue(args: dict) -> dict:
    """Update a Jira issue."""
    client = get_jira_client()
    issue_key = args["issue_key"]

    fields = {}
    if "summary" in args and args["summary"]:
        fields["summary"] = args["summary"]
    if "description" in args and args["description"]:
        fields["description"] = args["description"]
    if "labels" in args and args["labels"]:
        fields["labels"] = args["labels"]
    if "priority" in args and args["priority"]:
        fields["priority"] = args["priority"]

    if not fields:
        res = {"content": [{"type": "text", "text": "No fields to update"}]}
        await _send_result(res)
        return res

    try:
        await client.update_issue(issue_key, fields)
        res = {"content": [{"type": "text", "text": f"Updated issue {issue_key}"}]}
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error updating issue: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "add_comment",
    "Add a comment to a Jira issue.",
    {
        "issue_key": str,
        "comment": str
    }
)
async def jira_add_comment(args: dict) -> dict:
    """Add a comment to a Jira issue."""
    client = get_jira_client()
    issue_key = args["issue_key"]
    comment = args["comment"]

    try:
        await client.add_comment(issue_key, comment)
        res = {"content": [{"type": "text", "text": f"Added comment to {issue_key}"}]}
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error adding comment: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "transition_issue",
    "Transition a Jira issue to a new status (e.g., 'In Progress', 'Done', 'To Do').",
    {
        "issue_key": str,
        "transition_name": str
    }
)
async def jira_transition_issue(args: dict) -> dict:
    """Transition a Jira issue to a new status."""
    client = get_jira_client()
    issue_key = args["issue_key"]
    transition_name = args["transition_name"]

    try:
        result = await client.transition_issue(issue_key, transition_name)
        if "error" in result:
            res = {"content": [{"type": "text", "text": result["error"]}]}
            await _send_result(res)
            return res
        res = {"content": [{"type": "text", "text": f"Transitioned {issue_key} to '{transition_name}'"}]}
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error transitioning issue: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "get_project_issue_types",
    "Get available issue types for a Jira project.",
    {"project_key": str}
)
async def jira_get_project_issue_types(args: dict) -> dict:
    """Get issue types for a project."""
    client = get_jira_client()
    project_key = args["project_key"]

    try:
        result = await client.get_issue_types(project_key)
        types = [t["name"] for t in result.get("issueTypes", [])]
        res = {
            "content": [
                {"type": "text", "text": f"Issue types for {project_key}: {', '.join(types)}"}
            ]
        }
        await _send_result(res)
        return res
    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error getting issue types: {str(e)}"}]}
        await _send_result(res)
        return res


@tool(
    "search_past_meetings",
    "Search past meeting transcriptions for context using semantic search. Use this to find relevant discussions, decisions, or context from previous meetings that might be related to the current task.",
    {
        "query": str,
        "limit": int
    }
)
async def jira_search_past_meetings(args: dict) -> dict:
    """Search past meetings using semantic search."""
    query = args.get("query", "")
    limit = args.get("limit", 5)

    if not query:
        res = {"content": [{"type": "text", "text": "Please provide a search query."}]}
        await _send_result(res)
        return res

    if _meeting_search_fn is None:
        res = {"content": [{"type": "text", "text": "Meeting search is not configured."}]}
        await _send_result(res)
        return res

    try:
        results = await _meeting_search_fn(query, limit)

        if not results:
            res = {"content": [{"type": "text", "text": f"No past meetings found matching: {query}"}]}
            await _send_result(res)
            return res

        # Format results
        output_lines = [f"Found {len(results)} relevant meeting excerpts:\n"]
        for i, r in enumerate(results, 1):
            similarity_pct = int(r.get("similarity", 0) * 100)
            output_lines.append(f"--- Result {i} ({similarity_pct}% match) ---")
            output_lines.append(f"Meeting: {r.get('meeting_title', 'Unknown')}")
            output_lines.append(f"Project: {r.get('project_key', 'Unknown')}")
            output_lines.append(f"Date: {r.get('created_at', 'Unknown')}")
            output_lines.append(f"Content:\n{r.get('content', '')}\n")

        res = {"content": [{"type": "text", "text": "\n".join(output_lines)}]}
        await _send_result(res)
        return res

    except Exception as e:
        res = {"content": [{"type": "text", "text": f"Error searching meetings: {str(e)}"}]}
        await _send_result(res)
        return res


def create_jira_mcp_server():
    """Create an MCP server with all Jira tools."""
    return create_sdk_mcp_server(
        name="jira",
        version="1.0.0",
        tools=[
            jira_search,
            jira_get_issue,
            jira_create_issue,
            jira_update_issue,
            jira_add_comment,
            jira_transition_issue,
            jira_get_project_issue_types,
            jira_search_past_meetings
        ]
    )
