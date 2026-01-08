"""
GitLab API tools for fetching repository structure and code.
"""
import httpx
from typing import Optional, List, Dict, Any


class GitLabClient:
    """Client for interacting with GitLab API."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"PRIVATE-TOKEN": token}

    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make an authenticated request to GitLab API."""
        url = f"{self.base_url}/api/v4{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=self.headers, **kwargs)
            if not response.is_success:
                raise Exception(f"GitLab API error: HTTP {response.status_code} - {response.text[:500]}")
            return response.json()

    async def get_project(self, project_path: str) -> Dict:
        """Get project info by path (e.g., 'group/project')."""
        encoded_path = project_path.replace("/", "%2F")
        return await self._request("GET", f"/projects/{encoded_path}")

    async def get_repository_tree(
        self,
        project_path: str,
        path: str = "",
        ref: str = "main",
        recursive: bool = False
    ) -> List[Dict]:
        """Get the repository tree (file/folder structure)."""
        encoded_path = project_path.replace("/", "%2F")
        params = {"ref": ref, "recursive": str(recursive).lower()}
        if path:
            params["path"] = path
        return await self._request("GET", f"/projects/{encoded_path}/repository/tree", params=params)

    async def get_file_content(
        self,
        project_path: str,
        file_path: str,
        ref: str = "main"
    ) -> str:
        """Get the content of a file from the repository."""
        import base64
        encoded_project = project_path.replace("/", "%2F")
        encoded_file = file_path.replace("/", "%2F")
        data = await self._request(
            "GET",
            f"/projects/{encoded_project}/repository/files/{encoded_file}",
            params={"ref": ref}
        )
        # GitLab returns base64 encoded content
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content

    async def get_readme(self, project_path: str, ref: str = "main") -> Optional[str]:
        """Try to get the README file from the repository."""
        readme_names = ["README.md", "README.rst", "README.txt", "README"]
        for name in readme_names:
            try:
                return await self.get_file_content(project_path, name, ref)
            except Exception:
                continue
        return None

    async def search_files(
        self,
        project_path: str,
        search: str,
        ref: str = "main"
    ) -> List[Dict]:
        """Search for files in the repository by name pattern."""
        encoded_path = project_path.replace("/", "%2F")
        return await self._request(
            "GET",
            f"/projects/{encoded_path}/repository/tree",
            params={"ref": ref, "recursive": "true", "search": search}
        )


async def get_project_context(
    gitlab_url: str,
    gitlab_token: str,
    project_paths: List[str],
    max_files_per_project: int = 10
) -> str:
    """
    Fetch context from GitLab projects including structure and key files.
    Returns a formatted string with the repository context.
    """
    client = GitLabClient(gitlab_url, gitlab_token)
    context_parts = []

    for project_path in project_paths:
        project_path = project_path.strip()
        if not project_path:
            continue

        try:
            # Get project info
            project = await client.get_project(project_path)
            project_name = project.get("name", project_path)
            default_branch = project.get("default_branch", "main")

            context_parts.append(f"\n## GitLab Project: {project_name}")
            context_parts.append(f"Path: {project_path}")
            context_parts.append(f"Description: {project.get('description', 'No description')}")

            # Get README if available
            readme = await client.get_readme(project_path, default_branch)
            if readme:
                # Truncate if too long
                if len(readme) > 2000:
                    readme = readme[:2000] + "\n... (truncated)"
                context_parts.append(f"\n### README:\n```\n{readme}\n```")

            # Get repository structure (top-level only for now)
            try:
                tree = await client.get_repository_tree(project_path, ref=default_branch)
                files = [f"- {item['name']}/" if item['type'] == 'tree' else f"- {item['name']}"
                         for item in tree[:20]]
                context_parts.append(f"\n### Repository Structure:\n" + "\n".join(files))
            except Exception as e:
                context_parts.append(f"\n(Could not fetch repository structure: {e})")

            # Try to find key configuration files
            key_files = ["package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "pom.xml"]
            for key_file in key_files:
                try:
                    content = await client.get_file_content(project_path, key_file, default_branch)
                    if len(content) > 1500:
                        content = content[:1500] + "\n... (truncated)"
                    context_parts.append(f"\n### {key_file}:\n```\n{content}\n```")
                    break  # Only include one config file
                except Exception:
                    continue

        except Exception as e:
            context_parts.append(f"\n## GitLab Project: {project_path}")
            context_parts.append(f"Error fetching project: {e}")

    return "\n".join(context_parts) if context_parts else ""
