"""Public structural check available equally to every evaluated agent.

This is deliberately not the hidden correctness verifier.
"""

import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from execution import declared_script

sources = list(Path("src").rglob("*.py"))
result = Path("output/result.json")
assert sources or result.is_file(), "No Python source or result artifact provided"
for source in sources:
    ast.parse(source.read_text())
if result.exists():
    json.loads(result.read_text())
declared_script(Path.cwd())
