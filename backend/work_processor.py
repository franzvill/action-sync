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
        masked_url = f"https://oauth2:***@{gitlab_host}/{project_path}.git"
        project_name = project_path.split("/")[-1]
        target_dir = work_path / project_name

        if callback:
            await callback({"type": "text", "content": f"Cloning {project_path}...\n"})

        try:
            process = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", clone_url, str(target_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                if callback:
                    await callback({"type": "text", "content": f"Timeout cloning {project_path} (120s exceeded)\n"})
                continue

            if process.returncode == 0:
                if callback:
                    await callback({"type": "text", "content": f"Cloned {project_path}\n"})
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                # Mask the token in error messages to prevent leakage
                error_msg = error_msg.replace(clone_url, masked_url)
                if callback:
                    await callback({"type": "text", "content": f"Failed to clone {project_path}: {error_msg}\n"})
        except Exception as e:
            # Mask the token in exception messages to prevent leakage
            error_str = str(e).replace(clone_url, masked_url)
            if callback:
                await callback({"type": "text", "content": f"Error cloning {project_path}: {error_str}\n"})

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
