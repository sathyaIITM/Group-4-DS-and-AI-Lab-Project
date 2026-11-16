from .common import Contract
class SqlDraft(Contract):
    text: str
    model: str | None = None
    prompt_hash: str | None = None
class SqlAttempt(Contract):
    text: str = ""
    validation: str | None = None
    error: str | None = None
    generation: int = 1
