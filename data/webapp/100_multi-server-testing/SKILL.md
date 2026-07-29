---
name: multi-server-testing
description: Playwright skill for multi-server integration testing. Use it to run reproducible local web tests with controlled server lifecycle and fixtures.
license: Complete terms in LICENSE.txt
---

# Multi-server Integration Testing

## Objective

Use this skill to run reproducible local web tests with controlled server lifecycle and fixtures. Keep the scenario deterministic, safe to rerun, and independent of mutable public data.

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
2. Inspect helper usage with --help, start required services, wait for readiness, run the focused script, and clean up.
3. Assert a user-visible result and one underlying signal when useful.
4. Preserve focused diagnostics on failure.
5. Close browser contexts and temporary resources.

## Playwright Example

```python
# Inspect the helper before using it:
python scripts/with_server.py --help

# Start both services and run one browser script:
python scripts/with_server.py \
  --server "cd backend && python app.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- python tests/run_flow.py
```

## Failure Signals

- the target cannot be located by role, label, text, or a stable identifier;
- the page reaches the expected URL but renders the wrong state;
- the interface changes while the related request or persisted state fails;
- the script depends on an arbitrary sleep instead of an observable event.


## Common Pitfall

Unmanaged background servers can leave orphan processes and port conflicts.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
