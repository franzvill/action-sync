"""
Jira Processor

Processes meeting transcriptions and answers questions about Jira projects.
Uses custom Jira tools via the Claude Agent SDK.
"""

import re
import os
import shutil
import asyncio
from pathlib import Path
from typing import Callable, Any, Optional, Coroutine, List

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from jira_tools import JiraClient, set_jira_client, set_result_callback, set_meeting_search_fn, create_jira_mcp_server
from config import get_settings
from database import async_session_maker
from embedding_service import semantic_search

settings = get_settings()

# Directory to clone repos into
REPOS_DIR = Path("/tmp/repos")


async def clone_gitlab_repos(
    gitlab_url: str,
    gitlab_token: str,
    project_paths: List[str],
    callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None
) -> Path:
    """
    Clone GitLab repositories to a local directory.
    Returns the path to the repos directory.
    """
    print(f"[GitLab Clone] Starting clone process for {len(project_paths)} project(s)")
    print(f"[GitLab Clone] GitLab URL: {gitlab_url}")
    print(f"[GitLab Clone] Projects: {project_paths}")

    # Clean up and recreate repos directory
    if REPOS_DIR.exists():
        print(f"[GitLab Clone] Cleaning up existing repos directory: {REPOS_DIR}")
        shutil.rmtree(REPOS_DIR)
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[GitLab Clone] Created repos directory: {REPOS_DIR}")

    # Parse gitlab URL to get host
    gitlab_host = gitlab_url.rstrip("/").replace("https://", "").replace("http://", "")
    print(f"[GitLab Clone] Parsed host: {gitlab_host}")

    for project_path in project_paths:
        project_path = project_path.strip()
        if not project_path:
            continue

        # Build clone URL with token for auth (mask token in logs)
        clone_url = f"https://oauth2:{gitlab_token}@{gitlab_host}/{project_path}.git"
        masked_url = f"https://oauth2:***@{gitlab_host}/{project_path}.git"
        print(f"[GitLab Clone] Cloning: {masked_url}")

        # Get just the project name for the local folder
        project_name = project_path.split("/")[-1]
        target_dir = REPOS_DIR / project_name

        if callback:
            await callback({"type": "text", "content": f"📦 Cloning repository {project_path}...\n"})

        try:
            # Run git clone
            process = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", clone_url, str(target_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                print(f"[GitLab Clone] ✓ Successfully cloned {project_path} to {target_dir}")

                # List files in cloned directory
                files = list(target_dir.rglob("*"))
                file_count = len([f for f in files if f.is_file()])
                dir_count = len([f for f in files if f.is_dir()])
                print(f"[GitLab Clone] Directory contents: {file_count} files, {dir_count} directories")

                # Show top-level contents
                top_level = list(target_dir.iterdir())
                print(f"[GitLab Clone] Top-level items: {[f.name for f in top_level]}")

                if callback:
                    await callback({"type": "text", "content": f"✅ Cloned {project_path} ({file_count} files)\n"})
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                print(f"[GitLab Clone] ✗ Failed to clone {project_path}: {error_msg}")
                if callback:
                    await callback({"type": "text", "content": f"❌ Failed to clone {project_path}: {error_msg}\n"})
        except Exception as e:
            print(f"[GitLab Clone] ✗ Exception cloning {project_path}: {e}")
            if callback:
                await callback({"type": "text", "content": f"❌ Error cloning {project_path}: {e}\n"})

    # Final summary
    if REPOS_DIR.exists():
        all_repos = list(REPOS_DIR.iterdir())
        print(f"[GitLab Clone] Completed. Repos directory contains: {[r.name for r in all_repos]}")
        if callback:
            await callback({"type": "text", "content": f"📁 Repos ready at {REPOS_DIR}: {[r.name for r in all_repos]}\n\n"})

    return REPOS_DIR

JIRA_TOOLS = [
    "mcp__jira__search",
    "mcp__jira__get_issue",
    "mcp__jira__create_issue",
    "mcp__jira__update_issue",
    "mcp__jira__add_comment",
    "mcp__jira__transition_issue",
    "mcp__jira__get_project_issue_types",
    "mcp__jira__search_past_meetings",
    # File tools for exploring local repos
    "Read",
    "Glob",
    "Grep",
]


async def _run_claude_with_jira(
    prompt: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    message_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
    cwd: Optional[Path] = None,
    user_id: Optional[int] = None,
    project_key: Optional[str] = None
) -> str:
    """
    Run Claude with Jira tools and return the result text.
    """
    result_text = ""

    async def send_callback(data: dict):
        """Helper to safely call the async callback."""
        if message_callback:
            try:
                await message_callback(data)
            except Exception as e:
                print(f"Callback error: {e}")

    # Initialize the Jira client
    jira_client = JiraClient(jira_base_url, jira_email, jira_api_token)
    set_jira_client(jira_client)

    # Set callback for tool results
    set_result_callback(send_callback)

    # Set up meeting search function if user_id is available
    if user_id is not None:
        async def meeting_search_wrapper(query: str, limit: int = 5) -> list:
            """Wrapper for semantic search with user context."""
            async with async_session_maker() as db:
                results = await semantic_search(
                    db=db,
                    query=query,
                    user_id=user_id,
                    project_key=project_key,
                    limit=limit
                )
                return results
        set_meeting_search_fn(meeting_search_wrapper)

    # Create the MCP server with Jira tools
    jira_server = create_jira_mcp_server()

    options = ClaudeAgentOptions(
        max_turns=100,
        permission_mode="bypassPermissions",
        mcp_servers={"jira": jira_server},
        allowed_tools=JIRA_TOOLS,
        model=settings.azure_anthropic_model if settings.azure_anthropic_model else "claude-opus-4-5",
        cwd=cwd if cwd else None,
        env={
            "ANTHROPIC_BASE_URL": settings.azure_anthropic_endpoint,
            "ANTHROPIC_API_KEY": settings.azure_anthropic_api_key,
        },
    )

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

    return result_text


async def process_meeting_transcription(
    transcription: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    message_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
    gitlab_url: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    gitlab_projects: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    user_id: Optional[int] = None
) -> dict[str, Any]:
    """
    Process a meeting transcription using Claude to create/update Jira tickets.
    Optionally clones GitLab repositories for code context.
    """
    # Clone repos if configured
    repos_dir = None
    gitlab_section = ""
    if gitlab_url and gitlab_token and gitlab_projects:
        project_list = [p.strip() for p in gitlab_projects.split(",") if p.strip()]
        if project_list:
            # Clone the repositories
            repos_dir = await clone_gitlab_repos(
                gitlab_url, gitlab_token, project_list, message_callback
            )

            # Build list of cloned project names
            cloned_repos = [p.split("/")[-1] for p in project_list]
            gitlab_section = f"""

## Code Repository Context:
The following repositories have been cloned to your current working directory:
{chr(10).join(f'- ./{repo}/' for repo in cloned_repos)}

Use the Read, Glob, and Grep tools to explore the codebase and reference specific files,
classes, or modules in your ticket descriptions when discussing technical work.
"""

    # Build custom instructions section
    custom_section = ""
    if custom_instructions:
        custom_section = f"""

## Custom Instructions:
{custom_instructions}
"""

    prompt = f"""You are analyzing a meeting transcription to create and update Jira tickets.

## Meeting Transcription:
{transcription}

## Target Project: {project_key}
{gitlab_section}{custom_section}
## Your Task:
1. **Analyze** the transcription to identify:
   - Action items and tasks that need to be done
   - Decisions that were made
   - Issues or bugs mentioned
   - Any existing ticket references (like {project_key}-XXX)

2. **Search for existing tickets** in project {project_key} that might be relevant to the discussion.

3. **Update existing tickets** if they were mentioned or are clearly related:
   - Add comments with meeting notes
   - Update descriptions if new information was discussed
   - Change status if decisions were made

4. **Create new tickets** for new action items:
   - Use clear, actionable summaries
   - Include context from the meeting in the description
   - Use appropriate issue types (Task, Story, Bug, etc.)
   - Add the label "meeting-notes" to all created tickets
   {"- When technical work is discussed, use the Read/Glob/Grep tools to explore the local repos folder and reference specific files, classes, or modules in ticket descriptions" if gitlab_section else ""}
   - Use the search_past_meetings tool to find context from previous meetings when relevant (e.g., if something was discussed before)

5. **Provide a summary** of what you did:
   - List tickets updated (with keys and what was changed)
   - List tickets created (with keys and summaries)
   - Note any items that couldn't be processed

Be thorough but avoid creating duplicate tickets. Focus on actionable items.
"""

    try:
        result_text = await _run_claude_with_jira(
            prompt, jira_base_url, jira_email, jira_api_token, message_callback,
            cwd=repos_dir, user_id=user_id, project_key=project_key
        )

        # Parse the result to extract ticket information
        tickets_created = []
        if result_text:
            created_matches = re.findall(rf'{project_key}-\d+', result_text)
            tickets_created = list(set(created_matches))

        return {
            "success": True,
            "summary": result_text,
            "tickets_created": tickets_created,
            "tickets_updated": []
        }

    except Exception as e:
        if message_callback:
            await message_callback({"type": "error", "content": str(e)})
        return {
            "success": False,
            "error": str(e),
            "summary": f"Failed to process meeting: {str(e)}",
            "tickets_created": [],
            "tickets_updated": []
        }


async def ask_jira_question(
    question: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    message_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
    gitlab_url: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    gitlab_projects: Optional[str] = None,
    user_id: Optional[int] = None
) -> dict[str, Any]:
    """
    Ask a question about a Jira project and get an answer using Claude.
    Claude has access to Jira, past meeting history, and optionally the codebase.
    """
    # Clone repos if configured
    repos_dir = None
    codebase_section = ""
    if gitlab_url and gitlab_token and gitlab_projects:
        project_list = [p.strip() for p in gitlab_projects.split(",") if p.strip()]
        if project_list:
            # Clone the repositories
            repos_dir = await clone_gitlab_repos(
                gitlab_url, gitlab_token, project_list, message_callback
            )

            # Build list of cloned project names
            cloned_repos = [p.split("/")[-1] for p in project_list]
            codebase_section = f"""

## Codebase Access:
The following repositories have been cloned to your current working directory:
{chr(10).join(f'- ./{repo}/' for repo in cloned_repos)}

Use the Read, Glob, and Grep tools to explore the codebase when the question involves:
- Code structure, files, or architecture
- Implementation details
- Technical questions about how something works
"""

    prompt = f"""You are a helpful assistant that answers questions about a Jira project.

## Project: {project_key}

## User Question:
{question}

## Available Information Sources:
You have access to THREE sources of information to answer questions:

1. **Jira** - Use Jira tools (search, get_issue) to find tickets, issues, and project data
2. **Meeting History** - Use search_past_meetings to find context from past meeting transcriptions and discussions
3. **Codebase** - Use Read/Glob/Grep to explore the code when technical questions arise
{codebase_section}
## Instructions:
- Search across ALL relevant sources to provide comprehensive answers
- For questions about "what was discussed" or "what was decided", check meeting history first
- For questions about tickets, status, or project work, check Jira
- For questions about implementation or code, explore the codebase
- Combine information from multiple sources when relevant
- Be concise but thorough
- Format your answer clearly with bullet points or lists when appropriate
- Include issue keys (like {project_key}-123) when referencing specific tickets
- Reference specific files or code when answering technical questions

Answer the question now:
"""

    try:
        result_text = await _run_claude_with_jira(
            prompt, jira_base_url, jira_email, jira_api_token, message_callback,
            cwd=repos_dir, user_id=user_id, project_key=project_key
        )

        return {
            "success": True,
            "answer": result_text
        }

    except Exception as e:
        if message_callback:
            await message_callback({"type": "error", "content": str(e)})
        return {
            "success": False,
            "error": str(e),
            "answer": f"Failed to answer question: {str(e)}"
        }
