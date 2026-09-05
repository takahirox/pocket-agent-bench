Fix src/solution.py: slug(text) must lowercase ASCII text, replace each run of non-[a-z0-9] characters with one hyphen, and strip leading/trailing hyphens. Return empty string when nothing remains. Keep the public function name. Do not hard-code particular inputs.
Workspace: /app. Python 3 standard library and Git are available.
