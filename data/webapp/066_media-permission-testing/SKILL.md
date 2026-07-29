---
name: media-permission-testing
description: Playwright skill for camera and microphone permission testing. Use it to test permission-dependent browser features with deterministic context configuration.
license: Complete terms in LICENSE.txt
---

# Camera and Microphone Permission Testing

## Objective

Use this skill to test permission-dependent browser features with deterministic context configuration. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

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
- **Act:** Grant or deny the required permission before navigation, provide controlled values, and compare the resulting UI.
- **Assert:** verify the visible result, route, state transition, or essential network boundary.
- **Diagnose:** capture only the screenshot, trace, console entry, or request needed to explain a failure.
- **Clean up:** remove created records when fixtures are not disposable.

## Example

```python
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        geolocation={"latitude": 51.5074, "longitude": -0.1278}
    )
    context.grant_permissions(["geolocation"], origin="http://localhost:5173")
    page = context.new_page()
    page.goto("http://localhost:5173")
    expect(page.get_by_role("main")).to_be_visible()
    browser.close()
```

## Reliability Rules

Register event listeners before triggering events. Prefer locator, response, URL, popup, or download expectations over fixed delays.


## Common Pitfall

Interactive real browser prompts and hardware dependencies are unreliable in headless CI.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
