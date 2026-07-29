---
name: csp-behavior-testing
description: Playwright skill for content security policy behavior testing. Use it to validate safe browser-visible security behavior using controlled, non-destructive fixtures.
license: Complete terms in LICENSE.txt
---

# Content Security Policy Behavior Testing

## Objective

Use this skill to validate safe browser-visible security behavior using controlled, non-destructive fixtures. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

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
2. Inspect the relevant response or UI boundary, use harmless markers, and avoid production accounts or harmful payloads.
3. Assert a user-visible result and one underlying signal when useful.
4. Preserve focused diagnostics on failure.
5. Close browser contexts and temporary resources.

## Playwright Example

```python
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    response = page.goto("http://localhost:5173")
    assert response is not None
    assert "content-type" in response.headers
    expect(page.get_by_role("main")).to_be_visible()
    browser.close()
```

## Failure Signals

- the target cannot be located by role, label, text, or a stable identifier;
- the page reaches the expected URL but renders the wrong state;
- the interface changes while the related request or persisted state fails;
- the script depends on an arbitrary sleep instead of an observable event.


## Common Pitfall

Disabling the protection in the test environment defeats the purpose of the check.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
