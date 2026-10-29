"""Catalogue metadata used to build router states and generate labelled examples."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from analyst.decisions.kev_questions import Domain

CATALOGUE_PATH = Path("configs/catalogue.toml")


class CatalogueTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["real", "placeholder"]
    domain: Domain
    topic: str = ""
    line: str = ""
    publisher: str = ""
    resource_id: str = ""
    licence: str = ""
    retrieved: str = ""
    national_row: bool = False
    periods: list[str] = Field(default_factory=list)
    period_range: tuple[int, int] | None = None
    out_of_range_periods: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    place_aliases: dict[str, str] = Field(default_factory=dict)
    multi_places: dict[str, int] = Field(default_factory=dict)
    absent_breakdowns: list[str] = Field(default_factory=list)
    lacking_groups: list[str] = Field(default_factory=list)
    lacking_definitions: list[str] = Field(default_factory=list)
    describe_questions: list[str] = Field(default_factory=list)
    describe_templates: list[str] = Field(default_factory=list)


class UncoveredMeasure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str
    domain: Domain
    topic: str


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    table: list[CatalogueTable]
    uncovered: list[UncoveredMeasure]

    def real_tables(self) -> list[CatalogueTable]:
        return [t for t in self.table if t.status == "real"]

    def get(self, name: str) -> CatalogueTable:
        return next(t for t in self.table if t.name == name)


def load_catalogue(path: Path = CATALOGUE_PATH) -> Catalogue:
    with path.open("rb") as handle:
        return Catalogue.model_validate(tomllib.load(handle))
