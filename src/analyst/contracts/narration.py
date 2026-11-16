"""Narration (design document Section 4.6)."""

from analyst.contracts.common import CellRef, Contract


class NumberRef(Contract):
    text: str
    cell: CellRef | None
    derived_id: str | None


class Claim(Contract):
    text: str
    numbers: list[NumberRef]


class Narration(Contract):
    attempt: int
    text: str
    claims: list[Claim]
