import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from translate_schemas import AGENTS_DIR, TR, translate_schema


def extract_descriptions(obj, result=None):
    if result is None:
        result = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "description" and isinstance(v, str):
                result.add(v)
            elif isinstance(v, (dict, list)):
                extract_descriptions(v, result)
    elif isinstance(obj, list):
        for item in obj:
            extract_descriptions(item, result)
    return result


all_descs = set()
for agent_id in sorted(os.listdir(AGENTS_DIR)):
    agent_dir = os.path.join(AGENTS_DIR, agent_id)
    if not os.path.isdir(agent_dir):
        continue
    en_path = os.path.join(agent_dir, "schema.en.json")
    if not os.path.exists(en_path):
        continue
    with open(en_path) as f:
        schema = json.load(f)
    all_descs |= extract_descriptions(schema)

missing = [d for d in sorted(all_descs) if d not in TR]
print(f"Total descriptions: {len(all_descs)}")
print(f"In translation map: {len(TR)}")
print(f"MISSING: {len(missing)}")
print()
for d in missing:
    print(f"  {repr(d)},")
