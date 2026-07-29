---
name: form-validation-testing
description: Playwright skill for client-side form validation testing. Use it to validate labeled inputs, submission behavior, and field-level feedback.
license: Complete terms in LICENSE.txt
---

# Client-side Form Validation Testing

## Objective

Use this skill to validate labeled inputs, submission behavior, and field-level feedback. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

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
2. Fill controlled values, submit through the visible action, and verify validation or the resulting success state.
3. Assert a user-visible result and one underlying signal when useful.
4. Preserve focused diagnostics on failure.
5. Close browser contexts and temporary resources.

## Playwright Example

```python
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5173")
    page.get_by_label("Name").fill("Playwright Tester")
    page.get_by_label("Email").fill("tester@example.test")
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_role("status")).to_be_visible()
    browser.close()
```

## Failure Signals

- the target cannot be located by role, label, text, or a stable identifier;
- the page reaches the expected URL but renders the wrong state;
- the interface changes while the related request or persisted state fails;
- the script depends on an arbitrary sleep instead of an observable event.


## Common Pitfall

Submitting before validation settles can create timing-dependent failures.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
