# review-implementation review log 1

## Round 1 — 2026-11-09
**Findings**:
Now the knowledge base and source files.Reading the remaining tests to check acceptance-criteria coverage.`src/agent_workbench/apps/agent.py:172` — low — Every `TimeoutError` raised in a turn is reported as the idle-timeout message, even when neither `overall.expired()` nor `idle.expired()` is true. A builtin `TimeoutError` raised by the provider stack therefore skips `map_provider_error` and gets the wrong message. Fix: when neither timer expired, re-raise it so the generic `except Exception` branch maps it.
`vulture_whitelist.py:50` — low — The new `_.AGENT_MAX_STEPS` entry is not needed: `run_turn` uses the name in `recursion_limit`, so vulture never reports it. Its comment admits it is "used by run_turn". The issue only asks to whitelist names vulture actually reports, so remove the entry.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/agent_workbench/apps/agent.py around line 172, map a TimeoutError to the idle-timeout message only when idle.expired() is true, and to the overall-timeout message when overall.expired() is true. If neither timer has expired, re-raise it so the generic `except Exception` branch passes it through map_provider_error. Add a test where the provider raises a TimeoutError before either timer expires, and assert that the mapped provider error is reported, not the idle-timeout message.', 'Remove the `_.AGENT_MAX_STEPS` entry and its comment from vulture_whitelist.py:50. run_turn already uses the name, so vulture does not report it. Then run vulture to confirm it raises no new findings.'], escalate_reason=None)
**Changes**:
applied
