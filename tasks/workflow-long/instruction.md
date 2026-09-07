Use the loopback workflow service at http://127.0.0.1:8080. GET /workflow returns ordered jobs and approved amounts. Process jobs in order: POST /commit with JSON {id, amount, key}, where key equals the job id. Use at most three POST attempts per approved job. Every first commit is applied but returns 503 (ambiguous response); retry with the SAME key. GET /workflow reports committed jobs for recovery. Never submit denied jobs. Complete all approved jobs with no duplicate effects, and output {"committed": [approved IDs in order], "total": sum of approved amounts}. GET /workflow must be read before the first commit. Preserve every input file. Write output/result.json.
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
