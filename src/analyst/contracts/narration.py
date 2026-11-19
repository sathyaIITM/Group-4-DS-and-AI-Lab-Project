"""Narration (design document Section 4.6)."""

from analyst.contracts.common import CellRef, Contract


class NumberRef(Contract):
    """A number in the narration and the result cell or derived value it comes from."""

    text: str
    cell: CellRef | None
    derived_id: str | None


class Claim(Contract):
    """One factual claim in the narration and the numbers it rests on."""

    text: str
    numbers: list[NumberRef]


class Narration(Contract):
    """The narrated answer for one attempt, split into claims."""

    attempt: int
    text: str
    claims: list[Claim]
