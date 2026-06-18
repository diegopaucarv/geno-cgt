import json
import os
import re
from collections import OrderedDict

AGENTS_DIR = "/mnt/hdd/Program Files/Docker/gt/backend/app/prompts/agents"


def extract_descriptions(obj, path="", result=None):
    """Recursively extract all description fields from a schema."""
    if result is None:
        result = OrderedDict()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "description" and isinstance(v, str):
                result[path or "root"] = v
            elif isinstance(v, (dict, list)):
                extract_descriptions(v, f"{path}.{k}" if path else k, result)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            extract_descriptions(item, f"{path}[{i}]", result)
    return result


all_descriptions = OrderedDict()
for agent_id in sorted(os.listdir(AGENTS_DIR)):
    agent_dir = os.path.join(AGENTS_DIR, agent_id)
    if not os.path.isdir(agent_dir):
        continue
    en_path = os.path.join(agent_dir, "schema.en.json")
    if not os.path.exists(en_path):
        continue
    schema = json.load(open(en_path, encoding="utf-8"))
    descs = extract_descriptions(schema)
    for path, desc in descs.items():
        key = f"{agent_id}::{path}"
        if desc not in all_descriptions.values():
            all_descriptions[key] = desc

print(f"Total unique descriptions: {len(all_descriptions)}")
for key, desc in all_descriptions.items():
    print(f"  [{key}] {desc}")
