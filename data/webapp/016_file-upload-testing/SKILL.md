---
name: file-upload-testing
description: Playwright skill for file upload testing. Use it to test browser file selection, downloads, previews, and generated artifacts.
license: Complete terms in LICENSE.txt
---

# File Upload Testing

## Objective

Use this skill to test browser file selection, downloads, previews, and generated artifacts. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

## Operating Principles

- Use native Python Playwright APIs.
- Run bundled helper scripts with `--help` before relying on them.
- Register routes, listeners, and expectations before the triggering action.
- Prefer semantic locators and observable waits over arbitrary sleeps.
- Launch Chromium in headless mode unless another engine is explicitly required.
- Never expose secrets, submit real payments, or modify uncontrolled production data.
- Always close pages, contexts, and browsers.

## Recommended Workflow

1. Establish deterministic test data before opening the page.
2. Use a small local fixture, wrap the triggering action in the appropriate Playwright expectation, and inspect basic file properties.
3. Assert a user-visible result and one underlying signal when useful.
4. Preserve focused diagnostics on failure.
5. Close browser contexts and temporary resources.

## Playwright Example

```python
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

fixture = Path("fixtures/sample.txt")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5173")
    page.locator('input[type="file"]').set_input_files(fixture)
    expect(page.get_by_text(fixture.name)).to_be_visible()
    browser.close()
```

## Failure Signals

- the target cannot be located by role, label, text, or a stable identifier;
- the page reaches the expected URL but renders the wrong state;
- the interface changes while the related request or persisted state fails;
- the script depends on an arbitrary sleep instead of an observable event.


## Common Pitfall

Using a user-specific or external file makes the test non-portable.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
