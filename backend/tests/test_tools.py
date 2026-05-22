from pydantic import BaseModel, Field, ValidationError
from backend.agent.tools.base import BaseTool
from backend.agent.tools.github import GetLatestCommitsTool, GetRepoIssuesTool

# Dummy tool for testing base functionality
class DummySchema(BaseModel):
    required_str: str = Field(description="A required string parameter")
    optional_int: int = Field(default=42, description="An optional integer parameter")

class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "A simple dummy tool for tests"
    args_schema = DummySchema

    def _run(self, args: DummySchema) -> str:
        return f"Executed with: {args.required_str} and {args.optional_int}"


def test_base_tool_definition():
    tool = DummyTool()
    definition = tool.get_tool_definition()
    
    assert definition["type"] == "function"
    assert definition["function"]["name"] == "dummy_tool"
    assert definition["function"]["description"] == "A simple dummy tool for tests"
    
    params = definition["function"]["parameters"]
    assert "required_str" in params["properties"]
    assert "optional_int" in params["properties"]
    assert "title" not in params  # Check title cleanup
    assert "title" not in params["properties"]["required_str"]


def test_base_tool_execution_success():
    tool = DummyTool()
    # Pass valid arguments
    result = tool.execute(required_str="hello", optional_int=100)
    assert result == "Executed with: hello and 100"

    # Pass only required argument (defaults should kick in)
    result_default = tool.execute(required_str="world")
    assert result_default == "Executed with: world and 42"


def test_base_tool_execution_failure():
    tool = DummyTool()
    # Pass invalid argument types
    try:
        tool.execute(required_str=123, optional_int="not-an-int")
        raise AssertionError("Expected ValueError was not raised")
    except ValueError as e:
        assert "Invalid inputs for tool" in str(e)
    
    # Missing required argument
    try:
        tool.execute(optional_int=10)
        raise AssertionError("Expected ValueError was not raised")
    except ValueError as e:
        assert "Field required" in str(e) or "required_str" in str(e)


def test_github_tool_definitions():
    # Pass dummy token
    commits_tool = GetLatestCommitsTool(token="mock-token")
    issues_tool = GetRepoIssuesTool(token="mock-token")

    commit_def = commits_tool.get_tool_definition()
    assert commit_def["function"]["name"] == "get_latest_commits"
    assert "repo_name" in commit_def["function"]["parameters"]["required"]

    issue_def = issues_tool.get_tool_definition()
    assert issue_def["function"]["name"] == "get_repo_issues"
    assert "repo_name" in issue_def["function"]["parameters"]["required"]
    assert "state" in issue_def["function"]["parameters"]["properties"]

if __name__ == "__main__":
    print("🧪 Running BaseTool and GithubTool tests...")
    test_base_tool_definition()
    test_base_tool_execution_success()
    test_base_tool_execution_failure()
    test_github_tool_definitions()
    print("✅ All tests passed successfully!")
