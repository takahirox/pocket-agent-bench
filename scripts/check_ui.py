"""Optional browser acceptance check; requires Playwright + Chromium."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

report = Path(sys.argv[1]).resolve()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(report.as_uri())
    assert page.locator("#trials tr").count() > 0
    initial = page.locator("#trials tr").count()
    category = page.locator('#category option:not([value=""])').first.get_attribute("value")
    page.locator("#category").select_option(category)
    assert 0 < page.locator("#trials tr").count() <= initial
    page.locator("#trials button").first.click()
    assert page.locator("dialog").is_visible()
    assert page.locator("#detailbody").inner_text().find("採点根拠") >= 0
    page.locator(".close").click()
    page.locator("#category").select_option("")
    page.locator("#query").fill("not-a-task")
    assert page.locator("#trials tr").count() == 0
    page.locator("#query").fill("")
    comparison = page.evaluate("""() => {
      const jobs=[...new Set(all.map(r=>r.job))];
      if(jobs.length<2)return null;
      document.getElementById('baseline').value=jobs[0]; render();
      return [...document.querySelectorAll('#trials tr td:last-child')]
        .filter(e=>e.textContent.endsWith(' pt')).length;
    }""")
    if comparison:
        assert page.locator("#trials").inner_text().find("pt") >= 0
    page.screenshot(path=str(report.with_name("desktop.png")), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(report.with_name("mobile.png")), full_page=True)
    assert not errors, errors
    print(
        json.dumps(
            {
                "initial_trials": initial,
                "filter": True,
                "detail": True,
                "search": True,
                "javascript_errors": errors,
                "compared_rows": comparison,
            }
        )
    )
    browser.close()
