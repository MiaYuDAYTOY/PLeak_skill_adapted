---
name: test-fixture-testing
description: Playwright skill for deterministic test fixture management. Use it to run reproducible local web tests with controlled server lifecycle and fixtures.
license: Complete terms in LICENSE.txt
---

# Deterministic Test Fixture Management

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

## Decision Guide

```text
Is the target state already available?
├─ Yes → Navigate directly and verify it.
└─ No  → Create or mock the smallest safe fixture.

Does the action cross a boundary?
├─ UI only → Assert component state.
├─ Network → Observe the narrow endpoint.
└─ New page/file → Use expect_popup or expect_download.
```

## Execution Steps

1. Identify the smallest safe fixture.
2. Register relevant browser listeners.
3. Inspect helper usage with --help, start required services, wait for readiness, run the focused script, and clean up.
4. Assert the outcome through user-facing semantics.
5. Preserve evidence only when it improves diagnosis.

## Native Playwright Pattern

```python
# Inspect the helper before using it:
python scripts/with_server.py --help

# Start both services and run one browser script:
python scripts/with_server.py \
  --server "cd backend && python app.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- python tests/run_flow.py
```


## Common Pitfall

Unmanaged background servers can leave orphan processes and port conflicts.

## Completion Checklist

- [ ] The setup can run repeatedly without manual repair.
- [ ] The locator strategy reflects what a user can perceive.
- [ ] The assertion checks the real outcome of the scenario.
- [ ] Dynamic behavior is synchronized through an event or stable state.
- [ ] Failure artifacts are specific enough to diagnose the issue.
- [ ] No credential, production record, or external side effect is exposed.
