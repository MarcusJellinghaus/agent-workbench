"""Permission mode type: what the model may do with a tool or group."""

from typing import Literal

PermissionMode = Literal["allow", "ask", "ask_session", "deny"]
PERMISSION_MODES: tuple[PermissionMode, ...] = ("allow", "ask", "ask_session", "deny")
