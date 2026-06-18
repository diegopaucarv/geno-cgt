import json
import os
import re
import sys

PROMPTS_DIR = "/mnt/hdd/Program Files/Docker/gt/backend/app/prompts"
AGENTS_DIR = os.path.join(PROMPTS_DIR, "agents")

os.makedirs(AGENTS_DIR, exist_ok=True)


def extract_json_block(text):
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def parse_markdown_sections(body):
    sections = {}
    current_heading = None
    current_lines = []
    for line in body.split("\n"):
        if line.startswith("## "):
            if current_heading:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[3:].strip()
            current_lines = []
        elif current_heading:
            current_lines.append(line)
    if current_heading:
        sections[current_heading] = "\n".join(current_lines).strip()
    return sections


def extract_from_md(filepath):
    raw = open(filepath, encoding="utf-8").read()
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    body = parts[2].strip()
    sections = parse_markdown_sections(body)
    schema_section = sections.get("Output Schema", "")
    if schema_section:
        return extract_json_block(schema_section)
    return None


def extract_from_txt(filepath):
    raw = open(filepath, encoding="utf-8").read()
    in_schema = False
    schema_lines = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if in_schema:
            schema_lines.append(line)
        elif stripped == "---":
            in_schema = True
    schema_text = "\n".join(schema_lines).strip()
    if schema_text and schema_text.upper().startswith("SCHEMA"):
        schema_text = schema_text[len("SCHEMA") :].strip()
        schema_text = schema_text.replace("{{", "{").replace("}}", "}")
        try:
            return json.loads(schema_text)
        except json.JSONDecodeError:
            pass
    return None


# Load schemas from prompts/schemas.py
schemas_py_path = os.path.join(PROMPTS_DIR, "schemas.py")
schemas_py_source = open(schemas_py_path).read()
schemas_py_source = schemas_py_source.replace("from typing import Any", "")
exec(schemas_py_source)

py_schemas = {}
for k, v in list(locals().items()):
    if k.endswith("_SCHEMA") and isinstance(v, dict):
        py_schemas[k] = v

# The AGENT_SCHEMAS mapping
agent_schema_map = {}
for k, v in AGENT_SCHEMAS.items():
    agent_schema_map[k] = v

# Also from agents/schemas.py
agents_schemas_path = os.path.join(os.path.dirname(PROMPTS_DIR), "agents", "schemas.py")
agents_source = open(agents_schemas_path).read()
exec(agents_source)

agents_py_schemas = {}
for k, v in list(locals().items()):
    if k.endswith("_SCHEMA") and isinstance(v, dict) and k not in py_schemas:
        agents_py_schemas[k] = v

all_schemas = {}

# First: Python-defined schemas (most authoritative)
for agent_id, schema in {**agent_schema_map, **agents_py_schemas}.items():
    agent_id_clean = agent_id.replace("_SCHEMA", "").lower()
    all_schemas[agent_id_clean] = schema

# Then scan agents/ prompt.md files for schemas not already covered
agents_dir = os.path.join(PROMPTS_DIR, "agents")
if os.path.isdir(agents_dir):
    for agent_id in sorted(os.listdir(agents_dir)):
        agent_dir = os.path.join(agents_dir, agent_id)
        if not os.path.isdir(agent_dir):
            continue
        if agent_id in all_schemas:
            continue

        prompt_path = os.path.join(agent_dir, "prompt.md")
        if os.path.isfile(prompt_path):
            schema = extract_from_md(prompt_path)
            if schema:
                all_schemas[agent_id] = schema

# Write schemas
print(f"Total unique agents with schemas: {len(all_schemas)}")
for agent_id in sorted(all_schemas.keys()):
    schema = all_schemas[agent_id]
    agent_dir = os.path.join(AGENTS_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)

    en_path = os.path.join(agent_dir, "schema.en.json")
    with open(en_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    desc_count = str(schema).count('"description"')
    print(f"  OK {agent_id} ({desc_count} descriptions)")
