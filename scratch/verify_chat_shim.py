import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.llm_impl import SharedLLMClient

def test_chat_shim():
    print("Testing SharedLLMClient.chat shim...")
    client = SharedLLMClient()
    
    # Verify client has chat attribute and completions attribute
    assert hasattr(client, "chat"), "SharedLLMClient is missing 'chat' attribute!"
    chat = client.chat
    assert hasattr(chat, "completions"), "client.chat is missing 'completions' attribute!"
    completions = chat.completions
    
    # Mock litellm.completion to avoid hitting real APIs
    with patch("backend.core.llm_impl.litellm.completion") as mock_completion:
        mock_completion.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="test-response"))])
        
        # Test call
        response = completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "hello"}]
        )
        
        # Check mock call
        mock_completion.assert_called_once()
        print("Mock completion called successfully!")
        
        # Check response content
        content = response.choices[0].message.content
        assert content == "test-response", f"Expected 'test-response', got '{content}'"
        print("Response parsed successfully!")

    print("SharedLLMClient.chat verification passed! 🎉")

if __name__ == "__main__":
    try:
        test_chat_shim()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
