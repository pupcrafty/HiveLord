"""Strict JSON schema for final Dom Bot response."""
from typing import List, Optional
from pydantic import BaseModel, Field


class Action(BaseModel):
    """Represents an action taken or scheduled."""
    tool_name: str = Field(description="Name of the tool that was called")
    args: dict = Field(description="Arguments passed to the tool")
    result: dict = Field(description="Result from tool execution")
    task_id: Optional[str] = Field(default=None, description="Task ID if action was scheduled")


class MemoryWrite(BaseModel):
    """Represents a memory write operation."""
    key: str = Field(description="Memory key")
    value: str = Field(description="Memory value")
    metadata: Optional[dict] = Field(default=None, description="Optional metadata")


class DomBotResponse(BaseModel):
    """Final structured response from Dom Bot."""
    message: str = Field(description="Directive response to send immediately")
    actions: List[Action] = Field(default_factory=list, description="Every action taken/scheduled")
    memory_write: Optional[List[MemoryWrite]] = Field(default=None, description="DB writes (optional)")
    needs_followup: bool = Field(default=False, description="Whether a followup question is needed")
    followup_question: Optional[str] = Field(default=None, description="Followup question if needed")


def _inline_schema_refs(schema: dict) -> dict:
    """Inline $ref references and simplify anyOf for OpenAI strict mode compatibility."""
    if "$defs" not in schema:
        return _simplify_anyof(schema)
    
    defs = schema.pop("$defs", {})
    
    def resolve_ref(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_name = ref_path.replace("#/$defs/", "")
                    if def_name in defs:
                        # Recursively resolve nested refs
                        resolved = resolve_ref(defs[def_name].copy())
                        # Merge any additional properties
                        resolved.update({k: v for k, v in obj.items() if k != "$ref"})
                        return resolved
            return {k: resolve_ref(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_ref(item) for item in obj]
        else:
            return obj
    
    resolved = resolve_ref(schema)
    return _simplify_anyof(resolved)


def _simplify_anyof(schema: dict) -> dict:
    """Convert anyOf with null to simpler nullable format and fix strict mode requirements."""
    def simplify(obj, parent_obj=None, parent_key=None):
        if isinstance(obj, dict):
            # Handle anyOf with [type, {"type": "null"}]
            if "anyOf" in obj:
                anyof = obj["anyOf"]
                # Check if it's a nullable pattern: [{"type": "string"}, {"type": "null"}]
                if len(anyof) == 2:
                    types = [item.get("type") for item in anyof if isinstance(item, dict)]
                    if "null" in types:
                        # Extract the non-null type
                        non_null = [item for item in anyof if item.get("type") != "null"]
                        if len(non_null) == 1:
                            # Make it nullable by removing anyOf
                            simplified = non_null[0].copy()
                            # Keep other properties like default, description
                            for key in ["default", "description", "title"]:
                                if key in obj:
                                    simplified[key] = obj[key]
                            return simplify(simplified, parent_obj, parent_key)
            
            # First, recursively simplify nested objects
            simplified_obj = {}
            for k, v in obj.items():
                simplified_obj[k] = simplify(v, obj, k)
            
            # Then, for object types in strict mode, ensure additionalProperties is set
            if simplified_obj.get("type") == "object":
                # Set additionalProperties to false for strict mode (required by OpenAI)
                simplified_obj["additionalProperties"] = False
                
                # If it has properties, ensure required array matches exactly
                if "properties" in simplified_obj:
                    properties = simplified_obj.get("properties", {})
                    
                    # Check each property - if it's an empty object, remove from required
                    valid_required = []
                    for prop_name, prop_schema in properties.items():
                        # If property is an empty object (no properties defined), don't require it
                        if (isinstance(prop_schema, dict) and 
                            prop_schema.get("type") == "object" and 
                            not prop_schema.get("properties")):
                            # Empty object - skip adding to required
                            continue
                        valid_required.append(prop_name)
                    
                    if valid_required:
                        simplified_obj["required"] = sorted(valid_required)
                    else:
                        # No valid required properties - remove required array
                        if "required" in simplified_obj:
                            del simplified_obj["required"]
            
            return simplified_obj
        elif isinstance(obj, list):
            return [simplify(item, obj) for item in obj]
        else:
            return obj
    
    return simplify(schema)


def get_response_schema() -> dict:
    """Get the JSON schema for structured outputs with inlined references."""
    schema = DomBotResponse.model_json_schema()
    return _inline_schema_refs(schema)

