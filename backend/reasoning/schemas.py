"""
Schema Definitions for Human-in-the-Loop Suspend/Resume.

Inspired by Mastra's suspendSchema and resumeSchema concepts.
When a workflow suspends, it provides a schema defining what data it needs
from the human. When resuming, the frontend provides data matching that schema.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class FormField(BaseModel):
    name: str
    type: str  # "string", "boolean", "number", "select"
    label: str
    required: bool = True
    options: Optional[List[str]] = None  # For "select" type
    description: Optional[str] = None


class SuspendSchema(BaseModel):
    """Schema provided by the backend to the frontend when suspending execution."""
    type: str  # "approval", "selection", "form"
    title: str
    description: str
    fields: List[FormField]


# ── Common Suspend Schemas ──

def get_approval_schema(task_description: str) -> Dict[str, Any]:
    """Standard approval gate schema."""
    schema = SuspendSchema(
        type="approval",
        title="Human Approval Required",
        description=f"Please review and approve the following action: {task_description}",
        fields=[
            FormField(
                name="approved",
                type="boolean",
                label="Approve Execution",
                required=True,
                description="Check to approve, uncheck to reject."
            ),
            FormField(
                name="feedback",
                type="string",
                label="Feedback/Comments",
                required=False,
                description="Optional feedback for the agent."
            )
        ]
    )
    return schema.model_dump()


def get_selection_schema(title: str, description: str, options: List[str]) -> Dict[str, Any]:
    """Schema for selecting from multiple options."""
    schema = SuspendSchema(
        type="selection",
        title=title,
        description=description,
        fields=[
            FormField(
                name="selection",
                type="select",
                label="Choose an option",
                required=True,
                options=options
            )
        ]
    )
    return schema.model_dump()


def get_form_schema(title: str, description: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Custom form schema."""
    form_fields = [FormField(**f) for f in fields]
    schema = SuspendSchema(
        type="form",
        title=title,
        description=description,
        fields=form_fields
    )
    return schema.model_dump()
