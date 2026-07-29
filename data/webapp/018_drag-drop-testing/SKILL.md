---
name: drag-drop-testing
description: Playwright skill for drag and drop testing. Use it to exercise interactive components through visible controls and keyboard-compatible behavior.
license: Complete terms in LICENSE.txt
---

# Drag and Drop Testing

## Objective

Use this skill to exercise interactive components through visible controls and keyboard-compatible behavior. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

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
- **Act:** Trigger the component by role or label, wait for a semantic state change, and verify dismissal or persistence as appropriate.
- **Assert:** verify the visible result, route, state transition, or essential network boundary.
- **Diagnose:** capture only the screenshot, trace, console entry, or request needed to explain a failure.
- **Clean up:** remove created records when fixtures are not disposable.

## Example

```python
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5173")
    page.wait_for_load_state("domcontentloaded")
    expect(page.get_by_role("main")).to_be_visible()
    # Add the scenario-specific action and assertion.
    browser.close()
```

## Reliability Rules

Register event listeners before triggering events. Prefer locator, response, URL, popup, or download expectations over fixed delays.


## Common Pitfall

Raw coordinate clicks are fragile when layout or viewport dimensions change.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
