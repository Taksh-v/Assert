import os
import sys
sys.path.insert(0, os.path.abspath("."))

print("Importing litellm...")
import litellm
print("Importing langfuse...")
import langfuse
print("Importing backend.generation.llm_client...")
from backend.generation.llm_client import LLMClient
print("Importing backend.core.config...")
from backend.core.config import get_settings
print("Importing backend.reasoning.supervisor...")
from backend.reasoning.supervisor import SupervisorAgent
print("Done!")
