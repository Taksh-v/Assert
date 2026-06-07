from pydantic import BaseModel, Field
from .base import BaseTool


class GetLatestCommitsArgs(BaseModel):
    repo_name: str = Field(description="Repository name")
    max_commits: int = Field(default=5, description="Max commits to return")


class GetRepoIssuesArgs(BaseModel):
    repo_name: str = Field(description="Repository name")
    state: str = Field(default="open", description="Issue state")


class GetLatestCommitsTool(BaseTool):
    name = "get_latest_commits"
    description = "Return latest commits for a repository"
    args_schema = GetLatestCommitsArgs

    def _run(self, args: GetLatestCommitsArgs):
        # Return stubbed response for tests
        return [f"commit-{i}" for i in range(args.max_commits)]


class GetRepoIssuesTool(BaseTool):
    name = "get_repo_issues"
    description = "Return issues for a repository"
    args_schema = GetRepoIssuesArgs

    def _run(self, args: GetRepoIssuesArgs):
        # Return stubbed issues list
        return [{"id": 1, "title": "Issue 1", "state": args.state}]
