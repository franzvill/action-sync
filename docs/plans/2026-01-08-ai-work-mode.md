# AI Work Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Kanban board that shows Jira tickets, allowing users to pick a ticket and have Claude AI implement it automatically.

**Architecture:** New "Work" mode with Kanban UI, backend endpoints for fetching Jira workflow/tickets, and a work processor that clones repos and invokes Claude with git capabilities.

**Tech Stack:** FastAPI, SQLAlchemy, Claude Agent SDK, Vanilla JavaScript

---

## Task 1: Add kanban_jql Field to Database

**Files:**
- Modify: `backend/models.py:38-52`
- Modify: `backend/schemas.py:66-94`
- Modify: `backend/database.py` (migration)

**Step 1: Add field to JiraProject model**

In `backend/models.py`, add to JiraProject class after line 48:

```python
kanban_jql = Column(Text, nullable=True)  # JQL filter for Kanban board
```

**Step 2: Add field to schemas**

In `backend/schemas.py`, add to `JiraProjectCreate` (after embeddings_enabled):

```python
kanban_jql: Optional[str] = None  # JQL filter for Kanban board
```

Add to `JiraProjectResponse`:

```python
kanban_jql: Optional[str] = None
```

Add to `JiraProjectUpdate`:

```python
kanban_jql: Optional[str] = None
```

**Step 3: Update database migration in database.py**

Add migration for the new column in the `init_db` function (similar to existing migrations):

```python
# Add kanban_jql column if it doesn't exist
try:
    await conn.execute(text("ALTER TABLE jira_projects ADD COLUMN kanban_jql TEXT"))
except Exception:
    pass
```

**Step 4: Update server.py project creation**

In `add_jira_project` function, add:

```python
kanban_jql=project_data.kanban_jql
```

In `update_jira_project` function, add:

```python
if project_data.kanban_jql is not None:
    project.kanban_jql = project_data.kanban_jql if project_data.kanban_jql else None
```

**Step 5: Run and verify**

```bash
cd backend && python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
```

**Step 6: Commit**

```bash
git add backend/models.py backend/schemas.py backend/database.py backend/server.py
git commit -m "feat: add kanban_jql field to JiraProject model"
```

---

## Task 2: Add Jira Workflow Endpoint

**Files:**
- Modify: `backend/jira_tools.py` (add method to JiraClient)
- Modify: `backend/server.py` (add endpoint)

**Step 1: Add get_workflow_statuses method to JiraClient**

In `backend/jira_tools.py`, add method to `JiraClient` class:

```python
async def get_workflow_statuses(self, project_key: str) -> list[dict]:
    """Get all statuses available in a project's workflow."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{self.base_url}/rest/api/3/project/{project_key}/statuses",
            headers=self.headers
        )
        if not response.is_success:
            raise Exception(f"Failed to get workflow: {response.status_code}")

        data = response.json()
        # Extract unique statuses across all issue types
        statuses = {}
        for issue_type in data:
            for status in issue_type.get("statuses", []):
                status_id = status["id"]
                if status_id not in statuses:
                    statuses[status_id] = {
                        "id": status_id,
                        "name": status["name"],
                        "category": status.get("statusCategory", {}).get("key", "undefined")
                    }

        # Sort by category: to-do, in-progress, done
        category_order = {"new": 0, "indeterminate": 1, "done": 2}
        sorted_statuses = sorted(
            statuses.values(),
            key=lambda s: (category_order.get(s["category"], 1), s["name"])
        )
        return sorted_statuses
```

**Step 2: Add endpoint to server.py**

Add after the existing Jira Projects Routes section:

```python
# ============ Kanban Routes ============

@app.get("/api/jira/workflow/{project_key}")
async def get_workflow_statuses(
    project_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflow statuses for Kanban columns."""
    # Verify user has this project configured
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key.upper()
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")

    from jira_tools import JiraClient
    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        statuses = await client.get_workflow_statuses(project_key.upper())
        return {"statuses": statuses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 3: Test the endpoint**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/jira/workflow/PROJ
```

**Step 4: Commit**

```bash
git add backend/jira_tools.py backend/server.py
git commit -m "feat: add workflow statuses endpoint for Kanban"
```

---

## Task 3: Add Kanban Tickets Endpoint

**Files:**
- Modify: `backend/jira_tools.py`
- Modify: `backend/server.py`

**Step 1: Add search_issues method to JiraClient**

In `backend/jira_tools.py`, add to `JiraClient` class:

```python
async def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
    """Search for issues using JQL."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{self.base_url}/rest/api/3/search",
            headers=self.headers,
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,assignee,priority,issuetype,created,updated"
            }
        )
        if not response.is_success:
            raise Exception(f"Search failed: {response.status_code} - {response.text}")

        data = response.json()
        issues = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            assignee = fields.get("assignee")
            issues.append({
                "key": issue["key"],
                "summary": fields.get("summary", ""),
                "status": fields.get("status", {}).get("name", ""),
                "statusId": fields.get("status", {}).get("id", ""),
                "statusCategory": fields.get("status", {}).get("statusCategory", {}).get("key", ""),
                "assignee": assignee.get("displayName") if assignee else None,
                "assigneeAvatar": assignee.get("avatarUrls", {}).get("24x24") if assignee else None,
                "priority": fields.get("priority", {}).get("name", ""),
                "priorityIcon": fields.get("priority", {}).get("iconUrl", ""),
                "issueType": fields.get("issuetype", {}).get("name", ""),
                "issueTypeIcon": fields.get("issuetype", {}).get("iconUrl", ""),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", "")
            })
        return issues
```

**Step 2: Add kanban endpoint to server.py**

```python
@app.get("/api/jira/kanban/{project_key}")
async def get_kanban_tickets(
    project_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for Kanban board based on project's JQL filter."""
    # Get project with its settings
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key.upper()
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")

    # Build JQL - use custom or default
    if project.kanban_jql:
        jql = project.kanban_jql
    else:
        jql = f"project = {project_key.upper()} ORDER BY updated DESC"

    from jira_tools import JiraClient
    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        issues = await client.search_issues(jql)
        return {"issues": issues, "jql": jql}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 3: Commit**

```bash
git add backend/jira_tools.py backend/server.py
git commit -m "feat: add kanban tickets endpoint with JQL filtering"
```

---

## Task 4: Add Ticket Details Endpoint

**Files:**
- Modify: `backend/jira_tools.py`
- Modify: `backend/server.py`

**Step 1: Add get_issue_full method to JiraClient**

```python
async def get_issue_full(self, issue_key: str) -> dict:
    """Get full issue details including description and comments."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self.headers,
            params={"expand": "renderedFields"}
        )
        if not response.is_success:
            raise Exception(f"Failed to get issue: {response.status_code}")

        data = response.json()
        fields = data.get("fields", {})
        rendered = data.get("renderedFields", {})
        assignee = fields.get("assignee")
        reporter = fields.get("reporter")

        # Get comments
        comments = []
        for comment in fields.get("comment", {}).get("comments", []):
            author = comment.get("author", {})
            comments.append({
                "id": comment["id"],
                "body": comment.get("body", ""),
                "author": author.get("displayName", "Unknown"),
                "authorAvatar": author.get("avatarUrls", {}).get("24x24"),
                "created": comment.get("created", "")
            })

        return {
            "key": data["key"],
            "summary": fields.get("summary", ""),
            "description": fields.get("description"),  # ADF format
            "descriptionHtml": rendered.get("description", ""),  # Rendered HTML
            "status": fields.get("status", {}).get("name", ""),
            "statusId": fields.get("status", {}).get("id", ""),
            "priority": fields.get("priority", {}).get("name", ""),
            "issueType": fields.get("issuetype", {}).get("name", ""),
            "assignee": assignee.get("displayName") if assignee else None,
            "reporter": reporter.get("displayName") if reporter else None,
            "created": fields.get("created", ""),
            "updated": fields.get("updated", ""),
            "labels": fields.get("labels", []),
            "comments": comments
        }
```

**Step 2: Add endpoint to server.py**

```python
@app.get("/api/jira/ticket/{issue_key}")
async def get_ticket_details(
    issue_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full ticket details for the work panel."""
    # Extract project key from issue key
    project_key = issue_key.split("-")[0].upper()

    # Verify user has this project
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")

    from jira_tools import JiraClient
    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        ticket = await client.get_issue_full(issue_key)
        return ticket
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 3: Commit**

```bash
git add backend/jira_tools.py backend/server.py
git commit -m "feat: add ticket details endpoint"
```

---

## Task 5: Create Work Processor

**Files:**
- Create: `backend/work_processor.py`

**Step 1: Create work_processor.py**

```python
"""
Work Processor

Processes Jira tickets by having Claude implement them and push code to GitLab.
"""

import os
import shutil
import asyncio
from pathlib import Path
from typing import Callable, Any, Optional, Coroutine, List

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from jira_tools import JiraClient, set_jira_client, set_result_callback, create_jira_mcp_server
from config import get_settings

settings = get_settings()

# Directory to clone repos for work
WORK_DIR = Path("/tmp/work")


async def clone_repos_for_work(
    gitlab_url: str,
    gitlab_token: str,
    project_paths: List[str],
    issue_key: str,
    callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None
) -> Path:
    """
    Clone GitLab repositories for working on a ticket.
    Returns the path to the work directory.
    """
    # Create issue-specific work directory
    work_path = WORK_DIR / issue_key
    if work_path.exists():
        shutil.rmtree(work_path)
    work_path.mkdir(parents=True, exist_ok=True)

    gitlab_host = gitlab_url.rstrip("/").replace("https://", "").replace("http://", "")

    for project_path in project_paths:
        project_path = project_path.strip()
        if not project_path:
            continue

        clone_url = f"https://oauth2:{gitlab_token}@{gitlab_host}/{project_path}.git"
        project_name = project_path.split("/")[-1]
        target_dir = work_path / project_name

        if callback:
            await callback({"type": "text", "content": f"Cloning {project_path}...\n"})

        try:
            process = await asyncio.create_subprocess_exec(
                "git", "clone", clone_url, str(target_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                if callback:
                    await callback({"type": "text", "content": f"Cloned {project_path}\n"})
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                if callback:
                    await callback({"type": "text", "content": f"Failed to clone {project_path}: {error_msg}\n"})
        except Exception as e:
            if callback:
                await callback({"type": "text", "content": f"Error cloning {project_path}: {e}\n"})

    return work_path


# Tools available to Claude for work mode
WORK_TOOLS = [
    # Jira tools
    "mcp__jira__search",
    "mcp__jira__get_issue",
    "mcp__jira__create_issue",
    "mcp__jira__update_issue",
    "mcp__jira__add_comment",
    "mcp__jira__transition_issue",
    "mcp__jira__get_transitions",
    # File tools
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    # Shell for git
    "Bash",
]


async def process_work_ticket(
    ticket: dict,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    gitlab_url: str,
    gitlab_token: str,
    work_dir: Path,
    message_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
    custom_instructions: Optional[str] = None
) -> dict[str, Any]:
    """
    Have Claude work on a Jira ticket.
    """
    result_text = ""

    async def send_callback(data: dict):
        if message_callback:
            try:
                await message_callback(data)
            except Exception as e:
                print(f"Callback error: {e}")

    # Initialize Jira client
    jira_client = JiraClient(jira_base_url, jira_email, jira_api_token)
    set_jira_client(jira_client)
    set_result_callback(send_callback)

    # Create MCP server
    jira_server = create_jira_mcp_server()

    # Build the prompt
    custom_section = f"\n## Custom Instructions:\n{custom_instructions}\n" if custom_instructions else ""

    # List cloned repos
    repos = [d.name for d in work_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    repos_list = "\n".join(f"- ./{repo}/" for repo in repos)

    prompt = f"""You are an AI developer working on a Jira ticket.

## Ticket: {ticket['key']}
**Summary:** {ticket['summary']}
**Status:** {ticket['status']}
**Priority:** {ticket.get('priority', 'None')}
**Type:** {ticket.get('issueType', 'Task')}

**Description:**
{ticket.get('descriptionHtml', 'No description provided.')}

## Comments:
{_format_comments(ticket.get('comments', []))}

## Your Working Directory:
The following repositories have been cloned to your current directory:
{repos_list}

## GitLab Credentials:
When pushing, use these git push options to create a merge request:
```bash
git push -o merge_request.create -o merge_request.target=main origin <branch-name>
```
{custom_section}
## Your Task:

1. **Transition the ticket** to "In Progress" (or equivalent status)

2. **Analyze the ticket** and understand what needs to be done

3. **Identify the relevant repository** and files to modify

4. **Create a new branch** with a descriptive name based on the ticket

5. **Implement the changes** required by the ticket

6. **Commit your changes** with a clear commit message referencing the ticket

7. **Push the branch** with merge request creation:
   ```bash
   git push -o merge_request.create -o merge_request.target=main origin <branch-name>
   ```

8. **Add a comment to the Jira ticket** with:
   - Summary of what you implemented
   - Link to the merge request

9. **Transition the ticket** to "Code Review" (or equivalent status)

Work step by step. If you encounter any issues or the task is unclear, stop and explain what's blocking you rather than pushing incomplete work.
"""

    options = ClaudeAgentOptions(
        max_turns=100,
        permission_mode="bypassPermissions",
        mcp_servers={"jira": jira_server},
        allowed_tools=WORK_TOOLS,
        model=settings.azure_anthropic_model if settings.azure_anthropic_model else "claude-opus-4-5",
        cwd=work_dir,
        env={
            "ANTHROPIC_BASE_URL": settings.azure_anthropic_endpoint,
            "ANTHROPIC_API_KEY": settings.azure_anthropic_api_key,
        },
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for event in client.receive_response():
                event_type = type(event).__name__

                if event_type == "AssistantMessage":
                    for block in getattr(event, "content", []):
                        block_type = type(block).__name__
                        if block_type == "TextBlock":
                            text = getattr(block, "text", "")
                            result_text += text
                            await send_callback({"type": "text", "content": text})
                        elif block_type == "ToolUseBlock":
                            tool_name = getattr(block, "name", "unknown")
                            await send_callback({
                                "type": "tool_use",
                                "tool": tool_name,
                                "input": getattr(block, "input", {})
                            })

                elif event_type == "ToolResultMessage":
                    content = getattr(event, "content", "")
                    await send_callback({"type": "tool_result", "content": str(content)})

                elif event_type == "ResultMessage":
                    result_content = getattr(event, "result", "")
                    if result_content:
                        result_text = result_content
                    await send_callback({"type": "result", "content": result_text})

        return {
            "success": True,
            "summary": result_text
        }

    except Exception as e:
        if message_callback:
            await message_callback({"type": "error", "content": str(e)})
        return {
            "success": False,
            "error": str(e),
            "summary": f"Failed to process ticket: {str(e)}"
        }
    finally:
        # Cleanup work directory
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir)
        except Exception:
            pass


def _format_comments(comments: list) -> str:
    """Format comments for the prompt."""
    if not comments:
        return "No comments."

    formatted = []
    for c in comments[-5:]:  # Last 5 comments
        formatted.append(f"**{c['author']}** ({c['created'][:10]}):\n{c.get('body', '')}\n")
    return "\n".join(formatted)
```

**Step 2: Commit**

```bash
git add backend/work_processor.py
git commit -m "feat: add work processor for AI ticket implementation"
```

---

## Task 6: Add Work Start Endpoint

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/schemas.py`

**Step 1: Add WorkStartRequest schema**

In `backend/schemas.py`:

```python
# Work schemas
class WorkStartRequest(BaseModel):
    project_id: int
    issue_key: str
```

**Step 2: Add work endpoint to server.py**

Add import at top:

```python
from work_processor import clone_repos_for_work, process_work_ticket
```

Add endpoint:

```python
# ============ Work Mode Routes ============

@app.post("/api/work/start")
async def start_work(
    work_data: WorkStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start AI work on a Jira ticket."""
    if processing_state.is_processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another task is being processed. Please wait or abort it."
        )

    # Get project
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.id == work_data.project_id,
            JiraProject.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify issue belongs to project
    if not work_data.issue_key.upper().startswith(project.project_key):
        raise HTTPException(status_code=400, detail="Issue does not belong to this project")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")

    # Verify GitLab is configured
    if not jira_config.gitlab_url or not jira_config.gitlab_token:
        raise HTTPException(status_code=400, detail="GitLab not configured")

    if not project.gitlab_projects:
        raise HTTPException(status_code=400, detail="No GitLab repositories configured for this project")

    # Start processing
    processing_state.is_processing = True
    processing_state.current_user_id = current_user.id

    task = asyncio.create_task(
        _work_ticket_task(
            issue_key=work_data.issue_key.upper(),
            project_key=project.project_key,
            jira_base_url=jira_config.jira_base_url,
            jira_email=jira_config.jira_email,
            jira_api_token=jira_config.jira_api_token,
            gitlab_url=jira_config.gitlab_url,
            gitlab_token=jira_config.gitlab_token,
            gitlab_projects=project.gitlab_projects,
            custom_instructions=project.custom_instructions,
            user_id=current_user.id
        )
    )
    processing_state.current_task = task

    return {"status": "started"}


async def _work_ticket_task(
    issue_key: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    gitlab_url: str,
    gitlab_token: str,
    gitlab_projects: str,
    custom_instructions: Optional[str],
    user_id: int
):
    """Background task for AI ticket work."""
    from jira_tools import JiraClient

    async def message_callback(message: dict):
        await manager.send_message(user_id, message)

    try:
        # Get full ticket details
        await message_callback({"type": "text", "content": f"Fetching ticket {issue_key}...\n"})
        client = JiraClient(jira_base_url, jira_email, jira_api_token)
        ticket = await client.get_issue_full(issue_key)
        await message_callback({"type": "text", "content": f"Ticket: {ticket['summary']}\n\n"})

        # Clone repositories
        project_list = [p.strip() for p in gitlab_projects.split(",") if p.strip()]
        work_dir = await clone_repos_for_work(
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            project_paths=project_list,
            issue_key=issue_key,
            callback=message_callback
        )

        await message_callback({"type": "text", "content": "\nStarting AI work...\n\n"})

        # Process the ticket
        result = await process_work_ticket(
            ticket=ticket,
            project_key=project_key,
            jira_base_url=jira_base_url,
            jira_email=jira_email,
            jira_api_token=jira_api_token,
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            work_dir=work_dir,
            message_callback=message_callback,
            custom_instructions=custom_instructions
        )

        await manager.send_message(user_id, {
            "type": "complete",
            "success": result["success"],
            "summary": result.get("summary", "")
        })

    except asyncio.CancelledError:
        await manager.send_message(user_id, {"type": "aborted"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_message(user_id, {"type": "error", "error": str(e)})
    finally:
        processing_state.is_processing = False
        processing_state.current_task = None
        processing_state.current_user_id = None
```

**Step 3: Commit**

```bash
git add backend/server.py backend/schemas.py
git commit -m "feat: add work start endpoint"
```

---

## Task 7: Add Frontend Kanban State and API

**Files:**
- Modify: `frontend/static/js/app.js`

**Step 1: Add state variables**

Add to the `state` object (around line 15):

```javascript
// Work mode state
workMode: 'kanban',  // 'kanban' or 'detail' or 'working'
workStatuses: [],
workTickets: [],
workTicketsLoading: false,
selectedTicket: null,
selectedTicketLoading: false,
```

**Step 2: Add API functions**

Add after the meetings functions (around line 200):

```javascript
// =====================================================
// Work Mode Functions
// =====================================================

async function loadWorkflowStatuses(projectKey) {
    try {
        const data = await api(`/jira/workflow/${projectKey}`);
        state.workStatuses = data.statuses || [];
    } catch (e) {
        console.error('Failed to load workflow:', e);
        state.workStatuses = [];
    }
}

async function loadKanbanTickets(projectKey) {
    state.workTicketsLoading = true;
    render();
    try {
        const data = await api(`/jira/kanban/${projectKey}`);
        state.workTickets = data.issues || [];
    } catch (e) {
        console.error('Failed to load tickets:', e);
        showToast(e.message, 'error');
        state.workTickets = [];
    }
    state.workTicketsLoading = false;
    render();
}

async function loadTicketDetails(issueKey) {
    state.selectedTicketLoading = true;
    state.workMode = 'detail';
    render();
    try {
        state.selectedTicket = await api(`/jira/ticket/${issueKey}`);
    } catch (e) {
        showToast(e.message, 'error');
        state.selectedTicket = null;
        state.workMode = 'kanban';
    }
    state.selectedTicketLoading = false;
    render();
}

async function startWork(projectId, issueKey) {
    if (state.isProcessing) {
        showToast('Another task is processing', 'error');
        return;
    }

    state.isProcessing = true;
    state.workMode = 'working';
    state.logs = [];
    state.lastResult = null;
    render();

    try {
        await api('/work/start', {
            method: 'POST',
            body: JSON.stringify({ project_id: projectId, issue_key: issueKey })
        });
    } catch (e) {
        state.isProcessing = false;
        state.workMode = 'detail';
        showToast(e.message, 'error');
        render();
    }
}
```

**Step 3: Commit**

```bash
git add frontend/static/js/app.js
git commit -m "feat: add work mode state and API functions"
```

---

## Task 8: Add Frontend Kanban UI

**Files:**
- Modify: `frontend/static/js/app.js`

**Step 1: Add mode selector for Work**

Find the mode selector render function and add 'work' mode button.

In the `renderDashboard` or similar function, add the work mode tab:

```javascript
// In the mode selector section, add:
<button class="mode-btn ${state.mode === 'work' ? 'active' : ''}" onclick="setMode('work')">
    Work
</button>
```

**Step 2: Add setMode handler for 'work'**

Modify the `setMode` function:

```javascript
function setMode(mode) {
    state.mode = mode;
    if (mode === 'work' && state.selectedProject) {
        state.workMode = 'kanban';
        loadWorkflowStatuses(state.selectedProject);
        loadKanbanTickets(state.selectedProject);
    }
    render();
}
```

**Step 3: Add renderKanban function**

```javascript
function renderKanban() {
    if (state.workTicketsLoading) {
        return `<div class="loading">Loading tickets...</div>`;
    }

    if (state.workStatuses.length === 0) {
        return `<div class="empty-state">No workflow statuses found. Configure a project first.</div>`;
    }

    // Group tickets by status
    const ticketsByStatus = {};
    state.workStatuses.forEach(s => ticketsByStatus[s.id] = []);
    state.workTickets.forEach(t => {
        if (ticketsByStatus[t.statusId]) {
            ticketsByStatus[t.statusId].push(t);
        }
    });

    const columns = state.workStatuses.map(status => `
        <div class="kanban-column" data-status="${status.id}">
            <div class="kanban-column-header">
                <span class="status-name">${status.name}</span>
                <span class="status-count">${ticketsByStatus[status.id].length}</span>
            </div>
            <div class="kanban-cards">
                ${ticketsByStatus[status.id].map(ticket => `
                    <div class="kanban-card" onclick="loadTicketDetails('${ticket.key}')">
                        <div class="ticket-key">${ticket.key}</div>
                        <div class="ticket-summary">${escapeHtml(ticket.summary)}</div>
                        <div class="ticket-meta">
                            ${ticket.priorityIcon ? `<img src="${ticket.priorityIcon}" class="priority-icon" alt="${ticket.priority}">` : ''}
                            ${ticket.issueTypeIcon ? `<img src="${ticket.issueTypeIcon}" class="type-icon" alt="${ticket.issueType}">` : ''}
                            ${ticket.assigneeAvatar ? `<img src="${ticket.assigneeAvatar}" class="assignee-avatar" alt="${ticket.assignee}">` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');

    return `
        <div class="kanban-board">
            ${columns}
        </div>
    `;
}
```

**Step 4: Add renderTicketDetail function**

```javascript
function renderTicketDetail() {
    if (state.selectedTicketLoading) {
        return `<div class="loading">Loading ticket...</div>`;
    }

    const ticket = state.selectedTicket;
    if (!ticket) {
        return `<div class="error">Ticket not found</div>`;
    }

    const project = state.projects.find(p => p.project_key === state.selectedProject);

    return `
        <div class="ticket-detail-panel">
            <div class="ticket-detail-header">
                <button class="back-btn" onclick="state.workMode = 'kanban'; state.selectedTicket = null; render();">
                    ← Back to Board
                </button>
                <div class="ticket-key-large">${ticket.key}</div>
            </div>

            <h2 class="ticket-title">${escapeHtml(ticket.summary)}</h2>

            <div class="ticket-metadata">
                <div class="meta-item"><strong>Status:</strong> ${ticket.status}</div>
                <div class="meta-item"><strong>Priority:</strong> ${ticket.priority || 'None'}</div>
                <div class="meta-item"><strong>Type:</strong> ${ticket.issueType}</div>
                <div class="meta-item"><strong>Assignee:</strong> ${ticket.assignee || 'Unassigned'}</div>
            </div>

            <div class="ticket-description">
                <h3>Description</h3>
                <div class="description-content">
                    ${ticket.descriptionHtml || '<em>No description</em>'}
                </div>
            </div>

            <div class="ticket-comments">
                <h3>Comments (${ticket.comments.length})</h3>
                ${ticket.comments.length === 0 ? '<em>No comments</em>' : ticket.comments.map(c => `
                    <div class="comment">
                        <div class="comment-header">
                            ${c.authorAvatar ? `<img src="${c.authorAvatar}" class="comment-avatar">` : ''}
                            <strong>${escapeHtml(c.author)}</strong>
                            <span class="comment-date">${new Date(c.created).toLocaleDateString()}</span>
                        </div>
                        <div class="comment-body">${escapeHtml(JSON.stringify(c.body))}</div>
                    </div>
                `).join('')}
            </div>

            <div class="ticket-actions">
                <button class="btn-primary btn-large" onclick="startWork(${project?.id}, '${ticket.key}')" ${!project?.gitlab_projects ? 'disabled title="Configure GitLab repos first"' : ''}>
                    Start Work
                </button>
            </div>
        </div>
    `;
}
```

**Step 5: Add work mode rendering to main render**

In the main render logic for dashboard, add:

```javascript
// In renderDashboard or wherever modes are rendered:
if (state.mode === 'work') {
    if (state.workMode === 'kanban') {
        content = renderKanban();
    } else if (state.workMode === 'detail') {
        content = renderTicketDetail();
    } else if (state.workMode === 'working') {
        content = renderProcessingConsole(); // Reuse existing console
    }
}
```

**Step 6: Commit**

```bash
git add frontend/static/js/app.js
git commit -m "feat: add Kanban board and ticket detail UI"
```

---

## Task 9: Add Kanban CSS Styles

**Files:**
- Modify: `frontend/static/css/styles.css`

**Step 1: Add Kanban styles**

```css
/* =====================================================
   Kanban Board
   ===================================================== */

.kanban-board {
    display: flex;
    gap: 1rem;
    overflow-x: auto;
    padding: 1rem 0;
    min-height: 500px;
}

.kanban-column {
    flex: 0 0 280px;
    background: var(--surface-dark);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 250px);
}

.kanban-column-header {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
}

.status-count {
    background: var(--surface-light);
    padding: 0.125rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
}

.kanban-cards {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.kanban-card {
    background: var(--surface-light);
    border-radius: 6px;
    padding: 0.75rem;
    cursor: pointer;
    transition: transform 0.1s, box-shadow 0.1s;
    border: 1px solid transparent;
}

.kanban-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    border-color: var(--accent-color);
}

.ticket-key {
    font-size: 0.75rem;
    color: var(--accent-color);
    font-weight: 600;
    margin-bottom: 0.25rem;
}

.ticket-summary {
    font-size: 0.875rem;
    line-height: 1.4;
    margin-bottom: 0.5rem;
}

.ticket-meta {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.priority-icon,
.type-icon {
    width: 16px;
    height: 16px;
}

.assignee-avatar {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    margin-left: auto;
}

/* =====================================================
   Ticket Detail Panel
   ===================================================== */

.ticket-detail-panel {
    max-width: 800px;
    margin: 0 auto;
}

.ticket-detail-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
}

.back-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.5rem;
    font-size: 0.875rem;
}

.back-btn:hover {
    color: var(--text-primary);
}

.ticket-key-large {
    font-size: 0.875rem;
    color: var(--accent-color);
    font-weight: 600;
}

.ticket-title {
    font-size: 1.5rem;
    margin-bottom: 1rem;
}

.ticket-metadata {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1.5rem;
    padding: 1rem;
    background: var(--surface-dark);
    border-radius: 8px;
}

.meta-item {
    font-size: 0.875rem;
}

.ticket-description,
.ticket-comments {
    margin-bottom: 1.5rem;
}

.ticket-description h3,
.ticket-comments h3 {
    font-size: 1rem;
    margin-bottom: 0.75rem;
    color: var(--text-secondary);
}

.description-content {
    background: var(--surface-dark);
    padding: 1rem;
    border-radius: 8px;
    line-height: 1.6;
}

.comment {
    background: var(--surface-dark);
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 0.75rem;
}

.comment-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}

.comment-avatar {
    width: 24px;
    height: 24px;
    border-radius: 50%;
}

.comment-date {
    color: var(--text-secondary);
    font-size: 0.75rem;
    margin-left: auto;
}

.comment-body {
    font-size: 0.875rem;
    line-height: 1.5;
}

.ticket-actions {
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
}

.btn-large {
    padding: 1rem 2rem;
    font-size: 1rem;
}

.btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
```

**Step 2: Commit**

```bash
git add frontend/static/css/styles.css
git commit -m "feat: add Kanban board styles"
```

---

## Task 10: Add Settings Field for Kanban JQL

**Files:**
- Modify: `frontend/static/js/app.js`

**Step 1: Add JQL field to project settings form**

In the settings render function, find where project settings are displayed and add:

```javascript
// In the project settings section, add this field:
<div class="form-group">
    <label for="kanban-jql-${project.id}">Kanban JQL Filter</label>
    <input type="text"
           id="kanban-jql-${project.id}"
           value="${escapeHtml(project.kanban_jql || '')}"
           placeholder="e.g., status != Done AND assignee = currentUser()"
           onchange="updateProject(${project.id}, { kanban_jql: this.value })">
    <small>JQL query to filter which tickets appear on the Kanban board</small>
</div>
```

**Step 2: Commit**

```bash
git add frontend/static/js/app.js
git commit -m "feat: add Kanban JQL field to project settings"
```

---

## Task 11: Integration Testing

**Step 1: Start the server**

```bash
cd backend && python server.py
```

**Step 2: Test workflow endpoint**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/jira/workflow/PROJ
```

**Step 3: Test kanban endpoint**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/jira/kanban/PROJ
```

**Step 4: Test ticket details endpoint**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/jira/ticket/PROJ-1
```

**Step 5: Test the full UI flow**

1. Open http://localhost:8080
2. Login
3. Go to Settings, add GitLab repos to a project
4. Go to Dashboard, click "Work" mode
5. See Kanban board with tickets
6. Click a ticket to see details
7. Click "Start Work" to see AI process

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete AI Work Mode implementation"
```

---

## Summary

This implementation adds:

1. **Database**: `kanban_jql` field for custom JQL filtering
2. **Backend**: 4 new endpoints (workflow, kanban, ticket, work/start)
3. **Backend**: Work processor that clones repos and invokes Claude
4. **Frontend**: Kanban board with dynamic columns from Jira
5. **Frontend**: Ticket detail panel with "Start Work" button
6. **Frontend**: Settings field for Kanban JQL filter

Claude uses existing tools (Bash for git, Jira MCP tools, file tools) to implement tickets automatically.
