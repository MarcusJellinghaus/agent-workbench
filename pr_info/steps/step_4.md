# Step 4 – Permission gate (`apps/permission_gate.py`) and `build_graph(..., modes=...)`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`), and issue #18
(Scope "Binding" and "Interceptor", Constraints, Decisions). Implement step 4 only, test
first. Pattern: mcp_coder `src/mcp_coder/icoder/permissions/gateway.py` (`interceptor`) and
`src/mcp_coder/llm/providers/langchain/permission_bridge.py` – pattern only, not imported.
Run pylint, pytest (`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and
lint-imports until all pass. One commit.

Precondition: `langgraph.prebuilt.ToolNode.__init__` accepts `awrap_tool_call` and
`wrap_tool_call`, and `ToolCallRequest.runtime.config` exists. If not, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE
- New `src/agent_workbench/apps/permission_gate.py`
- `src/agent_workbench/apps/agent.py` (`build_graph`, `_open_runtime`)
- `src/agent_workbench/services/tool_call_log.py` (`_elapsed` → `elapsed`, module docstring)
- `tests/apps/conftest.py` (autouse fixture: app data in `tmp_path`)
- Tests: new `tests/apps/test_permission_gate.py`; every `build_graph` caller:
  `tests/apps/test_agent_graph.py`, `test_agent_tools.py`, `test_agent_turn.py`,
  `test_agent_checkpointer.py`, `test_ui_data_layer_delete.py`, `test_ui_handlers.py`

## WHAT
`apps/permission_gate.py`:
```python
TURN_PERMISSIONS_KEY = "turn_permissions"
DENY_USER = "Tool call denied by the user. Do not retry this call — choose a different approach, or ask the user what they would prefer."
DENY_UNAVAILABLE = "This tool requires approval, but no approval prompt was reachable, so the call was refused without asking the user. Choose a different approach or ask the user how to proceed."

Confirm = Callable[[str, dict[str, Any], PermissionMode], Awaitable[bool]]  # name, args, mode -> OK?

@dataclass(frozen=True)
class TurnPermissions:
    """Per-turn objects, passed by identity in configurable[TURN_PERMISSIONS_KEY]."""
    confirm: Confirm
    grants: set[str]          # ask_session grants of the conversation (tool names)
    lock: asyncio.Lock        # at most one dialog per turn

def deny_message(text: str, request: ToolCallRequest) -> ToolMessage: ...
async def gate_tool_call(request, execute, modes: Mapping[str, PermissionMode]) -> ToolMessage | Command
def deny_sync_tool_call(request, execute) -> ToolMessage
def make_tool_node(tools: Sequence[BaseTool], modes: Mapping[str, PermissionMode]) -> ToolNode
```
`agent.build_graph(chat_model, tools, checkpointer, *, modes: Mapping[str, PermissionMode]) -> Any`
uses `make_tool_node(tools, modes)` instead of `ToolNode(...)`. Required keyword, no default.

## ALGORITHM
`gate_tool_call` (outcomes logged with `log_tool_call(name, args, outcome, None, elapsed(start))`):
```
start = monotonic(); name, args = call["name"], call["args"]
if request.tool is None: log("blocked" if name in modes else "unknown_tool"); return await execute(request)
try: request.tool.args_schema.model_validate(args)   # args_schema is spec.args_model (a BaseModel class)
except ValidationError: log("invalid_arguments"); return await execute(request)
mode = modes[name]; if mode == "allow": return await execute(request)
turn = request.runtime.config.get("configurable", {}).get(TURN_PERMISSIONS_KEY)
if turn is None: log("denied"); return deny_message(DENY_UNAVAILABLE, request)
if not (mode == "ask_session" and name in turn.grants):
    try:
        async with turn.lock:
            approved = (mode == "ask_session" and name in turn.grants) or await turn.confirm(name, args, mode)
            if approved and mode == "ask_session": turn.grants.add(name)
    except asyncio.CancelledError: log("cancelled"); raise
    except Exception: logger.exception(...); log("dialog_error"); return deny_message(DENY_UNAVAILABLE, request)
    if not approved: log("denied"); return deny_message(DENY_USER, request)
return await execute(request)   # wrap_spec logs ok / error / cancelled
```
`deny_sync_tool_call`: log `denied` (duration 0-ish from entry), return
`deny_message(DENY_UNAVAILABLE, request)`; never calls `execute`.

`deny_message`: `ToolMessage(content=text, name=call["name"], tool_call_id=call["id"], status="error")`.

`make_tool_node`:
```
for tool in tools: if modes.get(tool.name, "deny") == "deny": raise ValueError(f"bound tool {tool.name!r} is missing from the modes or mapped to deny")
return ToolNode(list(tools), handle_tool_errors=True,
                awrap_tool_call=functools.partial(gate_tool_call, modes=modes),
                wrap_tool_call=deny_sync_tool_call)
```
Keep the existing `handle_tool_errors=True` comment from `build_graph`.

## HOW
- `BaseTool.args_schema` is typed `ArgsSchema | None`: validate only when it is a pydantic
  model class (`isinstance(schema, type) and issubclass(schema, BaseModel)`); for our tools it
  always is (`to_structured_tool` passes `spec.args_model`).
- `_open_runtime` (transitional until step 5): `enabled = {s.name for s in enabled_specs(toolsets.specs)}`;
  `modes = {s.name: "allow" if s.name in enabled else "deny" for s in toolsets.specs}` (`{}` without toolsets);
  pass `modes=modes` to `build_graph`.
- `tool_call_log.py`: rename `_elapsed` → `elapsed` (used by `wrap_spec` and the gate).
  Module docstring: calls that fail before `fn` runs (unknown or `deny` tool, invalid
  arguments) and calls that are denied or cancelled before running are logged by
  `apps.permission_gate`; drop the "#18's permission node" sentence.
- Existing `build_graph` callers in tests pass `modes={...}` explicitly (`{}` for no tools,
  `{tool.name: "allow"}` for their tools) – nothing allowed by omission.
- Test isolation of the gate's audit log: the gate now logs calls that don't run (e.g.
  `unknown_tool` in `test_agent_graph.py::test_unknown_tool_call_routes_to_tool_node`), and
  no fixture redirects app data today. Add an autouse fixture to `tests/apps/conftest.py`
  that patches `agent_workbench.adapters.config.app_data_dir` to return the test's
  `tmp_path`, so no test writes to the real `~/.agent_workbench/logs/tool_calls.jsonl`.
  Tests that patch it themselves (e.g. the `app_data` fixture of `test_agent_tools.py`)
  keep working: their patch is applied on top, to the same `tmp_path`.

## DATA
- `modes`: `{tool name: PermissionMode}` for every configured spec, `deny` included.
- Gate returns `execute`'s `ToolMessage` / `Command`, or a denial `ToolMessage`.

## Tests (write first) – `tests/apps/test_permission_gate.py`
Direct calls of `gate_tool_call` with a stub `execute` and a `ToolCallRequest` (real
`StructuredTool` from a fake spec, `runtime` with a `config` dict), app data patched to
`tmp_path` to read `tool_calls.jsonl`:
- outcomes: `deny` tool → `blocked`; unknown name → `unknown_tool`; invalid args →
  `invalid_arguments` and confirm not called; Cancel → `denied`; confirm returning False
  after a timeout (`None` → False in step 7) → `denied`; no `TurnPermissions` → `denied` with
  `DENY_UNAVAILABLE`; confirm raising → `dialog_error` with `DENY_UNAVAILABLE`; task
  cancelled during confirm → `cancelled`, `CancelledError` raised; task cancelled while
  waiting for the lock (lock held by the test) → `cancelled`.
- denial `ToolMessage`: `status == "error"`, matching `tool_call_id`, `DENY_USER` /
  `DENY_UNAVAILABLE` text.
- logged duration of a denied call includes the dialog wait (confirm sleeps ~0.2 s → `duration_s >= 0.2`).
- `ask_session`: one grants set → confirm called once for two calls; Cancel not remembered
  (second call asks again); a fresh set asks again.
- two `ask` calls gathered concurrently → dialogs do not overlap (confirm records
  enter/exit order); two `ask_session` calls of the same tool gathered → confirm called once.
Graph level (`build_graph` with the scripted fake model and fake provider, `ainvoke` with
`{"configurable": {"thread_id": ..., TURN_PERMISSIONS_KEY: TurnPermissions(...)}}`):
- `allow` runs; `ask` OK runs, Cancel returns `DENY_USER` with the call's id; one message
  with an allowed and a denied call handles both.
- a call to a `deny` tool gets `ToolNode`'s invalid-tool text, which names the bound tools
  and no other `deny` tool (the text echoes the requested name).
- sync: `make_tool_node(...).invoke({"messages": [AIMessage(tool_calls=[...])]})` runs no
  tool and logs `denied`.
- `build_graph` raises `ValueError` for a bound tool missing from `modes` and for one mapped to `deny`.
