from pydantic import Field
from .common import Contract
class Narration(Contract):
    text: str = ""
    claims: tuple[dict[str, object], ...] = ()
