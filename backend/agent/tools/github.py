import logging
from typing import Dict, Any, List
from github import Github
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GithubTool:
    """
    Direct API access for GitHub.
    Used by agents for real-time data fetching.
    """

    def __init__(self, token: str):
        self.client = Github(token)

    def get_repo_issues(self, repo_name: str, state: str = "open") -> List[Dict[str, Any]]:
        """Fetch open issues from a repository."""
        try:
            repo = self.client.get_repo(repo_name)
            issues = repo.get_issues(state=state)
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
            logger.error(f"GitHub tool error: {e}")
            return []

    def get_latest_commits(self, repo_name: str) -> List[Dict[str, Any]]:
        """Fetch latest commits from a repository."""
        try:
            repo = self.client.get_repo(repo_name)
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
            logger.error(f"GitHub tool error: {e}")
            return []
