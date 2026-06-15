"""
Dynamic Schema Generator — A9 del plan de implementación.

Genera JSON Schemas en runtime a partir de variables derivadas del POOL.
Equivalente al Structured Output Parser6 de My workflow 2.json (n8n).

Permite que el sistema clasifique documentos según un codebook de variables
sin necesidad de redeploy de prompts cuando se añaden nuevas variables.
"""

from __future__ import annotations

import json
from typing import Any


class DynamicSchemaGenerator:
    """
    Genera JSON Schemas en runtime desde variables derivadas.

    Uso:
        gen = DynamicSchemaGenerator()
        schema = gen.generate_classification_schema(variables)
        # schema se inyecta como output format en un prompt de clasificación
    """

    def generate_classification_schema(self, variables: list[dict]) -> dict:
        """
        Para cada variable, genera una propiedad en el schema
        con enum de sus categorías.

        Args:
            variables: lista de dicts con:
                - variable_code: str
                - measurement_level: str ("Binary", "Nominal", "Ordinal", "Continuous")
                - categories: list[dict] con value_code, label
                - definition: str (opcional)

        Returns:
            JSON Schema listo para usar como output format.
        """
        properties: dict[str, Any] = {}

        for var in variables:
            code = var.get("variable_code", "")
            level = var.get("measurement_level", "Nominal")
            cats = var.get("categories", [])
            definition = var.get("definition", code)

            if not code:
                continue

            if level in ("Binary", "Nominal") and cats:
                properties[code] = {
                    "type": "string",
                    "enum": [c.get("value_code", c.get("label", "")) for c in cats],
                    "description": definition,
                }
            elif level == "Ordinal":
                properties[code] = {
                    "type": "string",
                    "description": f"{definition} (ordinal: {', '.join(c.get('label', '') for c in cats)})",
                }
            elif level == "Continuous":
                properties[code] = {
                    "type": "number",
                    "description": definition,
                }
            else:
                properties[code] = {
                    "type": "string",
                    "description": definition,
                }

        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties.keys()),
        }

    def build_classification_prompt_variables(
        self, document: dict, variables: list[dict]
    ) -> dict:
        """
        Construye las variables para un prompt de clasificación de documentos.

        Args:
            document: dict con 'text' (str) y opcionalmente 'name' (str)
            variables: lista de variables del POOL

        Returns:
            dict con 'document_text' y 'classification_schema' listos para .format()
        """
        schema = self.generate_classification_schema(variables)
        return {
            "document_text": document.get("text", "")[:8000],
            "document_name": document.get("name", ""),
            "classification_schema": json.dumps(schema, indent=2, ensure_ascii=False),
        }

    def get_variable_labels(self, variables: list[dict]) -> dict[str, str]:
        """
        Devuelve un mapa variable_code → label para UI.
        Útil para mostrar nombres legibles en el frontend.
        """
        return {
            var.get("variable_code", ""): var.get(
                "definition", var.get("variable_code", "")
            )
            for var in variables
            if var.get("variable_code")
        }
