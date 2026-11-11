"""WebSocket protocol v1 between the UI and a kernel session.

Client -> server: `execute`, `interrupt`, `restart`.
Server -> client: `status`, `execute_input`, `output`, `clear_output`,
`execute_reply`, `error`. Every frame is a JSON object carrying `v` and `type`.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

KernelState = Literal["starting", "idle", "busy", "restarting", "dead"]
ReplyStatus = Literal["ok", "error", "aborted"]


class _Frame(BaseModel):
    v: Literal[1] = 1


class ExecuteRequest(_Frame):
    type: Literal["execute"] = "execute"
    cell_id: str
    code: str
    language: Literal["python", "sql", "duckdb"] = "python"


class InterruptRequest(_Frame):
    type: Literal["interrupt"] = "interrupt"


class RestartRequest(_Frame):
    type: Literal["restart"] = "restart"


ClientMessage = Annotated[
    ExecuteRequest | InterruptRequest | RestartRequest,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class StatusEvent(_Frame):
    type: Literal["status"] = "status"
    state: KernelState


class ExecuteInputEvent(_Frame):
    type: Literal["execute_input"] = "execute_input"
    cell_id: str
    execution_count: int | None = None


class OutputEvent(_Frame):
    type: Literal["output"] = "output"
    cell_id: str
    output: dict[str, Any]


class ClearOutputEvent(_Frame):
    type: Literal["clear_output"] = "clear_output"
    cell_id: str
    wait: bool = False


class ExecuteReplyEvent(_Frame):
    type: Literal["execute_reply"] = "execute_reply"
    cell_id: str
    status: ReplyStatus
    execution_count: int | None = None


class ErrorEvent(_Frame):
    type: Literal["error"] = "error"
    code: str
    message: str


ServerEvent = (
    StatusEvent | ExecuteInputEvent | OutputEvent | ClearOutputEvent | ExecuteReplyEvent | ErrorEvent
)
