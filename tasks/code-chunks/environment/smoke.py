"""Public structural check available equally to every evaluated agent.

This is deliberately not the hidden correctness verifier.
"""

import ast
import json
from pathlib import Path

source = Path("src/solution.py")
if source.exists():
    ast.parse(source.read_text())
else:
    json.loads(Path("output/result.json").read_text())
