"""Exercise a standalone report in an installed Chromium, without a Python browser SDK."""

import json
import re
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path

report, browser = map(Path, sys.argv[1:3])
acceptance = r"""
<script>
try {
  const assert=(ok,message)=>{if(!ok)throw Error(message)};
  assert(all.length>0,'missing trials');
  const initial=document.querySelectorAll('#trials tr').length;
  assert(initial===all.length,'initial trial count');
  const cohorts=[...new Set(all.map(r=>r.cohort))];
  document.getElementById('cohort').value=cohorts[0];render();
  assert(document.querySelectorAll('#trials tr').length===all.filter(r=>r.cohort===cohorts[0]).length,'suite filter');
  document.querySelector('#trials button').click();
  assert(document.getElementById('detail').open,'trial detail');
  document.getElementById('detail').close();
  document.getElementById('cohort').value='';
  const difficulty=all[0].difficulty;
  document.getElementById('difficulty').value=difficulty;render();
  assert(document.querySelectorAll('#trials tr').length===all.filter(r=>r.difficulty===difficulty).length,'difficulty filter');
  document.getElementById('difficulty').value='';
  document.getElementById('query').value='not-a-task';render();
  assert(document.querySelectorAll('#trials tr').length===0,'search');
  document.getElementById('query').value='';render();
  const result=document.createElement('pre');result.id='browser-acceptance';
  result.textContent=JSON.stringify({ok:true,trials:initial,suite_selections:cohorts.length});
  document.body.appendChild(result);
} catch(error) {
  const result=document.createElement('pre');result.id='browser-acceptance';
  result.textContent=JSON.stringify({ok:false,error:String(error)});document.body.appendChild(result);
}
</script>
"""
with tempfile.TemporaryDirectory(prefix="pocket-report-browser-") as directory:
    folder = Path(directory)
    page = folder / "report.html"
    page.write_text(report.read_text().replace("</html>", acceptance + "</html>"))
    result = subprocess.run(
        [
            str(browser),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-extensions",
            f"--user-data-dir={folder / 'profile'}",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    match = re.search(r'<pre id="browser-acceptance">(.*?)</pre>', result.stdout, re.DOTALL)
    assert match, "Browser did not execute report acceptance assertions"
    evidence = json.loads(unescape(match[1]))
    assert evidence["ok"], evidence
    print(json.dumps(evidence))
