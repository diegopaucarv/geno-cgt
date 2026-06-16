"""ToolRegistry: registro centralizado de herramientas para agentes.

Uso:
    registry = ToolRegistry()
    registry.register(search_segments, "search_segments", "Busca segmentos...")
    result = registry.execute("search_segments", {"query": "...", "top_k": 5})

    # O con el decorador @tool:
    @tool(name="search_segments", description="Busca segmentos...",
          parameters={"query": "texto", "proyecto_id": "UUID"})
    def search_segments(query, proyecto_id, top_k=5):
        ...
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def tool(name: str, description: str, parameters: dict[str, str] | None = None):
    """Decorador para registrar funciones como tools usables por agentes.

    La metadata se guarda en fn._tool_meta y es leída por
    ToolRegistry.register_from_module().
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._tool_meta = {  # type: ignore[attr-defined]
            "name": name,
            "description": description,
            "parameters": parameters or {},
        }
        return fn

    return decorator


class ToolRegistry:
    """Registro centralizado de tools disponibles para agentes.

    Cada tool es una función Python que:
    - Recibe kwargs según sus parameters
    - Retorna un dict (que se serializa a JSON string para el LLM)

    El método execute() valida que la tool existe, la invoca,
    y devuelve el resultado como string JSON para el agente.
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        fn: Callable[..., Any],
        name: str,
        description: str,
        parameters: dict[str, str] | None = None,
    ) -> None:
        """Registra una función como tool."""
        self._tools[name] = {
            "fn": fn,
            "name": name,
            "description": description,
            "parameters": parameters or {},
        }

    def register_from_module(self, module: Any) -> int:
        """Auto-registra todas las funciones decoradas con @tool de un módulo.

        Returns:
            Número de tools registradas.
        """
        count = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, "_tool_meta"):
                meta = attr._tool_meta
                self.register(
                    attr,
                    meta["name"],
                    meta["description"],
                    meta["parameters"],
                )
                count += 1
        return count

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Ejecuta una tool y devuelve el resultado como string JSON.

        Args:
            tool_name: Nombre de la tool a ejecutar.
            tool_input: Diccionario con los parámetros.

        Returns:
            String JSON con el resultado o un error.
        """
        if tool_name not in self._tools:
            available = list(self._tools.keys())
            return json.dumps(
                {
                    "error": f"Tool '{tool_name}' not found.",
                    "available": available,
                },
                ensure_ascii=False,
            )

        try:
            fn = self._tools[tool_name]["fn"]
            result = fn(**tool_input)
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False, default=str)
            return str(result)
        except TypeError as e:
            logger.error("Tool %s bad params: %s", tool_name, e)
            return json.dumps(
                {
                    "error": f"Bad parameters for '{tool_name}': {e}",
                    "expected": self._tools[tool_name]["parameters"],
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def get_schema_for_prompt(self) -> str:
        """Genera la descripción de tools para el system prompt del agente."""
        lines: list[str] = []
        for name, info in self._tools.items():
            params = json.dumps(info["parameters"], ensure_ascii=False)
            lines.append(f"- {name}({params}): {info['description']}")
        return "\n".join(lines)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convierte las tools a formato OpenAI/ Together.ai function calling.

        Útil para native function calling (más robusto que text parsing).
        """
        tools: list[dict[str, Any]] = []
        for name, info in self._tools.items():
            properties: dict[str, dict[str, str]] = {}
            for param_name, param_desc in info["parameters"].items():
                properties[param_name] = {
                    "type": "string",
                    "description": param_desc,
                }
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": list(info["parameters"].keys()),
                        },
                    },
                }
            )
        return tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
