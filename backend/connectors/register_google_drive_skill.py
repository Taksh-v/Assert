from backend.connectors.skill_registry import register_skill

GOOGLE_DRIVE_LIST_INPUT = {
    "type": "object",
    "properties": {
        "folder_id": {"type": "string"},
        "modified_since": {"type": "string", "format": "date-time"}
    },
    "required": []
}

GOOGLE_DRIVE_LIST_OUTPUT = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object"}},
    }
}


def register():
    register_skill(
        "google_drive.list",
        input_schema=GOOGLE_DRIVE_LIST_INPUT,
        output_schema=GOOGLE_DRIVE_LIST_OUTPUT,
        metadata={"idempotent": False, "timeout_seconds": 30}
    )


register()
