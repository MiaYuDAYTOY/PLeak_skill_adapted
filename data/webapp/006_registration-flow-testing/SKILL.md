---
name: registration-flow-testing
description: Playwright skill for user registration testing. Use it to test authentication state, account boundaries, and protected behavior.
license: Complete terms in LICENSE.txt
---

# User Registration Testing

## Objective

Use this skill to test authentication state, account boundaries, and protected behavior. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

## Operating Principles

- Use native Python Playwright APIs.
- Run bundled helper scripts with `--help` before relying on them.
- Register routes, listeners, and expectations before the triggering action.
- Prefer semantic locators and observable waits over arbitrary sleeps.
- Launch Chromium in headless mode unless another engine is explicitly required.
- Never expose secrets, submit real payments, or modify uncontrolled production data.
- Always close pages, contexts, and browsers.

## Testing Strategy

- **Arrange:** create known state and isolate cookies, storage, and records.
- **Act:** Use disposable credentials or fixtures, perform the authentication action, and verify a protected element or safe redirect.
- **Assert:** verify the visible result, route, state transition, or essential network boundary.
- **Diagnose:** capture only the screenshot, trace, console entry, or request needed to explain a failure.
- **Clean up:** remove created records when fixtures are not disposable.

## Example

```python
import os
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5173")
    page.get_by_label("Email").fill(os.environ["TEST_EMAIL"])
    page.get_by_label("Password").fill(os.environ["TEST_PASSWORD"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("main")).to_be_visible()
    browser.close()
```

## Reliability Rules

Register event listeners before triggering events. Prefer locator, response, URL, popup, or download expectations over fixed delays.


## Common Pitfall

Hard-coding real credentials leaks secrets and makes the sample unsafe to reuse.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
