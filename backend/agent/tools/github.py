import logging
from typing import Dict, Any, List
from github import Github
from pydantic import BaseModel, Field
from backend.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

# ── Pydantic Schemas ─────────────────────────────────────
class GetRepoIssuesSchema(BaseModel):
    repo_name: str = Field(description="The full repository name in 'owner/repo' format (e.g., 'google/jax')")
    state: str = Field(default="open", description="State of the issues to fetch: 'open', 'closed', or 'all'")

class GetLatestCommitsSchema(BaseModel):
    repo_name: str = Field(description="The full repository name in 'owner/repo' format (e.g., 'google/jax')")


# ── Schema-Driven Tools ──────────────────────────────────
class GetRepoIssuesTool(BaseTool):
    """Tool to fetch issues from a GitHub repository."""
    name = "get_repo_issues"
    description = "Fetch recent issues from a GitHub repository with filter options"
    args_schema = GetRepoIssuesSchema

    def __init__(self, token: str):
        self.client = Github(token)

    def _run(self, args: GetRepoIssuesSchema) -> List[Dict[str, Any]]:
        try:
            repo = self.client.get_repo(args.repo_name)
            issues = repo.get_issues(state=args.state)
            return [
                {
                    "number": i.number,
                    "title": i.title,
                    "state": i.state,
                    "url": i.html_url,
                    "created_at": i.created_at.isoformat()
                }
                for i in issues[:10]
            ]
        except Exception as e:
            logger.error(f"GitHub tool error in get_repo_issues: {e}")
            return []


class GetLatestCommitsTool(BaseTool):
    """Tool to fetch latest commits from a GitHub repository."""
    name = "get_latest_commits"
    description = "Fetch the most recent commits from a GitHub repository"
    args_schema = GetLatestCommitsSchema

    def __init__(self, token: str):
        self.client = Github(token)

    def _run(self, args: GetLatestCommitsSchema) -> List[Dict[str, Any]]:
        try:
            repo = self.client.get_repo(args.repo_name)
            commits = repo.get_commits()
            return [
                {
                    "sha": c.sha[:7],
                    "author": c.commit.author.name,
                    "message": c.commit.message,
                    "date": c.commit.author.date.isoformat()
                }
                for c in commits[:5]
            ]
        except Exception as e:
            logger.error(f"GitHub tool error in get_latest_commits: {e}")
            return []


# ── Legacy Wrapper (For Backwards Compatibility) ─────────
class GithubTool:
    """
    Legacy direct API access for GitHub.
    Preserved for backward compatibility, internally delegates to the schema-driven tools.
    """

    def __init__(self, token: str):
        self.token = token
        self.issues_tool = GetRepoIssuesTool(token)
        self.commits_tool = GetLatestCommitsTool(token)

    def get_repo_issues(self, repo_name: str, state: str = "open") -> List[Dict[str, Any]]:
        """Fetch open issues from a repository."""
        return self.issues_tool.execute(repo_name=repo_name, state=state)

    def get_latest_commits(self, repo_name: str) -> List[Dict[str, Any]]:
        """Fetch latest commits from a repository."""
        return self.commits_tool.execute(repo_name=repo_name)
