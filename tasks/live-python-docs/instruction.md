Retrieve today's Python documentation through GET http://127.0.0.1:8080/live. This trusted service fetches https://docs.python.org/3/ and returns the actual HTML, sha256, title and URL, recording the source snapshot independently. Return {url, title, sha256} exactly as observed. Do not substitute remembered facts. Upstream failure makes the trial unscorable. This is a live-web retrieval/evidence workload, distinct from browser interaction. Preserve every input file. Write output/result.json.
Workspace: /app. Python 3 standard library and Git are available.

Optional execution transport (pocket-python-v1), identical for every configuration:
You may perform the API workflow directly, OR author a Python program under src/
and output/execute.json containing exactly {"script":"src/your_program.py"}.
If declared, after your final response the harness runs that program ONCE in /app
as the unprivileged agent, using the remaining aggregate time budget. It must perform
the requested operations and write output/result.json itself. Python's standard
library is available. The harness does not infer a program or supply an answer.
Do not both perform state-changing API calls now and declare a program that repeats
them. Internal structural smoke checks do not run the program. This transport is
optional; a final response alone is not the required result artifact.
