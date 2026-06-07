import dlt
from dlt.sources.rest_api import rest_api_source

def test_slack_dlt_yield():
    source = rest_api_source(
        config={
            "client": {
                "base_url": "https://slack.com/api/",
                "auth": {
                    "type": "bearer",
                    "token": "invalid-token"
                }
            },
            "resources": [
                {
                    "name": "channels",
                    "endpoint": {
                        "path": "conversations.list",
                        "params": {"types": "public_channel", "limit": 1},
                        "data_selector": "channels"
                    }
                }
            ]
        }
    )
    
    try:
        # Just iterate directly
        for item in source.resources["channels"]:
            print(item)
    except Exception as e:
        print("Expected auth error:", type(e), e)

test_slack_dlt_yield()
