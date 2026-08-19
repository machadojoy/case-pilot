"""Shared pagination: the query params dependency and the response envelope."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel

# Plain BaseModel rather than SQLModel: this is a pure wire envelope with no table
# behind it, and generics sit awkwardly on the SQLModel metaclass.


class Page[T](BaseModel):
    """One page of results plus enough context for a client to navigate.

    `total` is the full row count, not the page size — it costs a COUNT(*) per
    request, which is cheap at our scale and is what a UI needs to render "page
    3 of 12". Revisit if a table ever gets large enough for the count to hurt.
    """

    items: list[T]
    total: int
    offset: int
    limit: int


@dataclass
class PaginationParams:
    """`?offset=&limit=` with sane bounds.

    A dataclass (not a Pydantic model) so FastAPI reads the fields as individual
    query parameters rather than expecting a request body.
    """

    offset: Annotated[int, Query(ge=0)] = 0
    limit: Annotated[int, Query(ge=1, le=100)] = 20


PaginationDep = Annotated[PaginationParams, Depends()]
