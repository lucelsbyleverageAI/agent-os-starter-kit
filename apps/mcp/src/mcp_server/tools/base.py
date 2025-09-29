"""Base classes for MCP tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Tool parameter definition."""

    name: str
    type: str  # "string", "number", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, Any]] = None


class ToolDefinition(BaseModel):
    """Tool definition for MCP protocol."""

    name: str
    description: str
    parameters: List[ToolParameter] = []
    toolkit: Optional[str] = None
    toolkit_display_name: Optional[str] = None
    
    def to_mcp_schema(self) -> Dict[str, Any]:
        """Convert to MCP tool schema format."""
        properties = {}
        required = []
        
        for param in self.parameters:
            param_schema = {
                "type": param.type,
                "description": param.description,
            }
            
            if param.type == "array" and param.items:
                param_schema["items"] = param.items
            
            if param.enum:
                param_schema["enum"] = param.enum
            
            if param.default is not None:
                param_schema["default"] = param.default
                
            properties[param.name] = param_schema
            
            if param.required:
                required.append(param.name)
        
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        
        # Add toolkit information if available
        if self.toolkit:
            schema["function"]["toolkit"] = self.toolkit
        if self.toolkit_display_name:
            schema["function"]["toolkit_display_name"] = self.toolkit_display_name
            
        return schema


class BaseTool(ABC):
    """Base class for all tools."""

    def __init__(self) -> None:
        self._definition: Optional[ToolDefinition] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        pass

    @property
    def definition(self) -> ToolDefinition:
        """Get tool definition."""
        if self._definition is None:
            self._definition = ToolDefinition(
                name=self.name,
                description=self.description,
                parameters=self.get_parameters(),
                toolkit=self.get_toolkit_name(),
                toolkit_display_name=self.get_toolkit_display_name(),
            )
        return self._definition
    
    def get_toolkit_name(self) -> Optional[str]:
        """Get toolkit name - can be overridden by subclasses."""
        return None
    
    def get_toolkit_display_name(self) -> Optional[str]:
        """Get toolkit display name - can be overridden by subclasses."""
        return None

    @abstractmethod
    def get_parameters(self) -> List[ToolParameter]:
        """Get tool parameters."""
        pass

    @abstractmethod
    async def execute(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the tool.
        
        Args:
            user_id: The user ID executing the tool
            **kwargs: Tool input parameters
            
        Returns:
            Tool execution result
        """
        pass

    def validate_input(self, **kwargs: Any) -> Dict[str, Any]:
        """Validate tool input parameters."""
        validated = {}
        
        for param in self.get_parameters():
            value = kwargs.get(param.name)
            
            if param.required and value is None:
                raise ValueError(f"Required parameter '{param.name}' is missing")
            
            if value is not None:
                # Basic type validation
                if param.type == "string" and not isinstance(value, str):
                    raise ValueError(f"Parameter '{param.name}' must be a string")
                elif param.type == "integer" and not isinstance(value, int):
                    raise ValueError(f"Parameter '{param.name}' must be an integer")
                elif param.type == "number" and not isinstance(value, (int, float)):
                    raise ValueError(f"Parameter '{param.name}' must be a number")
                elif param.type == "boolean" and not isinstance(value, bool):
                    raise ValueError(f"Parameter '{param.name}' must be a boolean")
                elif param.type == "array" and not isinstance(value, list):
                    raise ValueError(f"Parameter '{param.name}' must be an array")
                elif param.type == "object" and not isinstance(value, dict):
                    raise ValueError(f"Parameter '{param.name}' must be an object")
                
                # Enum validation
                if param.enum and value not in param.enum:
                    raise ValueError(
                        f"Parameter '{param.name}' must be one of {param.enum}"
                    )
                
                validated[param.name] = value
            elif param.default is not None:
                validated[param.name] = param.default
        
        return validated


class ArcadeTool(BaseTool):
    """Base class for Arcade tools."""

    def __init__(self, arcade_tool_name: str, arcade_definition: Any) -> None:
        super().__init__()
        self.arcade_tool_name = arcade_tool_name
        self.arcade_definition = arcade_definition

    @property
    def name(self) -> str:
        """Tool name."""
        return self.arcade_tool_name

    @property
    def description(self) -> str:
        """Tool description."""
        return self.arcade_definition.description or f"Arcade tool: {self.arcade_tool_name}"
    
    def get_toolkit_name(self) -> Optional[str]:
        """Get toolkit name from Arcade definition."""
        if hasattr(self.arcade_definition, 'toolkit') and self.arcade_definition.toolkit:
            return self.arcade_definition.toolkit.name.lower()
        return "arcade"
    
    def get_toolkit_display_name(self) -> Optional[str]:
        """Get toolkit display name from Arcade definition."""
        if hasattr(self.arcade_definition, 'toolkit') and self.arcade_definition.toolkit:
            return self.arcade_definition.toolkit.name
        return "Arcade"

    def get_parameters(self) -> List[ToolParameter]:
        """Get tool parameters from Arcade definition."""
        parameters = []
        
        if hasattr(self.arcade_definition, 'input') and self.arcade_definition.input:
            if hasattr(self.arcade_definition.input, 'parameters'):
                for param in self.arcade_definition.input.parameters or []:
                    # Skip non-inferrable parameters for now
                    if hasattr(param, 'inferrable') and param.inferrable is False:
                        continue
                        
                    param_type = self._convert_arcade_type(param.value_schema.val_type)
                    
                    items_schema = None
                    if param_type == "array":
                        # Check for item schema in the Arcade definition
                        if hasattr(param.value_schema, 'item_schema') and param.value_schema.item_schema:
                            item_type = self._convert_arcade_type(param.value_schema.item_schema.val_type)
                            items_schema = {"type": item_type}
                        else:
                            # Fallback for arrays of strings if item schema is not defined
                            items_schema = {"type": "string"}
                    
                    parameters.append(ToolParameter(
                        name=param.name,
                        type=param_type,
                        description=param.description or "No description provided",
                        required=param.required,
                        items=items_schema,
                    ))
        
        return parameters

    def _convert_arcade_type(self, arcade_type: str) -> str:
        """Convert Arcade type to MCP type."""
        type_mapping = {
            "string": "string",
            "number": "number",
            "integer": "integer",
            "boolean": "boolean",
            "array": "array",
            "json": "object",
        }
        return type_mapping.get(arcade_type, "string")

    async def execute(self, user_id: str, user_email: Optional[str] = None, **kwargs: Any) -> Any:
        """Execute the Arcade tool."""
        from ..auth.arcade_auth import arcade_auth_manager
        
        # Validate input
        validated_input = self.validate_input(**kwargs)
        
        # Execute via Arcade auth manager
        return arcade_auth_manager.execute_tool(
            user_id=user_id,
            tool_name=self.arcade_tool_name,
            tool_input=validated_input,
            user_email=user_email
        )


class CustomTool(BaseTool):
    """Base class for custom tools."""
    
    # Class-level toolkit definition that can be overridden
    toolkit_name: str = "custom"
    toolkit_display_name: str = "Custom Tools"

    @property
    def name(self) -> str:
        """Tool name - should be overridden by subclasses."""
        return f"custom_{self.__class__.__name__.lower()}"
    
    def get_toolkit_name(self) -> Optional[str]:
        """Get toolkit name for custom tools."""
        return self.toolkit_name
    
    def get_toolkit_display_name(self) -> Optional[str]:
        """Get toolkit display name for custom tools."""
        return self.toolkit_display_name

    async def execute(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the custom tool - should be overridden by subclasses."""
        # Validate input
        validated_input = self.validate_input(**kwargs)
        
        # Pass through special arguments that start with _ (like _jwt_token, _context_*)
        # These are internal arguments used for authentication and context passing
        for key, value in kwargs.items():
            if key.startswith('_') and key not in validated_input:
                validated_input[key] = value
        
        # Call the actual implementation
        return await self._execute_impl(user_id, **validated_input)

    @abstractmethod
    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Actual tool implementation - must be overridden by subclasses."""
        pass 