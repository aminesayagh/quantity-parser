from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

Status = Literal["resolved", "ambiguous", "unsupported", "invalid"]
Form = Literal["integer", "decimal", "fraction", "mixed_number", "ordinal"]
Kind = Literal["number", "ordinal", "multiplier", "percentage"]
KINDS: tuple[Kind, ...] = ("number", "ordinal", "multiplier", "percentage")


@dataclass(frozen=True)
class Quantity:
    """value is exact; form is how it was written; kind is how it is meant."""

    value: Fraction
    form: Form
    kind: Kind

    def to_dict(self) -> dict:
        return {
            "value": {"numerator": self.value.numerator, "denominator": self.value.denominator},
            "form": self.form,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ParseResult:
    """`quantity` is set only when status is "resolved".

    `interpretations` lists the competing readings when status is "ambiguous",
    for inspection only; callers must not pick one silently.
    `span` is a zero-based, end-exclusive offset pair into `source`.
    """

    status: Status
    source: str
    quantity: Quantity | None = None
    span: tuple[int, int] | None = None
    reason: str | None = None
    interpretations: tuple[Quantity, ...] = ()

    def to_dict(self) -> dict:
        d = {
            "status": self.status,
            "quantity": self.quantity.to_dict() if self.quantity else None,
            "source": self.source,
            "span": list(self.span) if self.span else None,
            "reason": self.reason,
        }
        if self.interpretations:
            d["interpretations"] = [q.to_dict() for q in self.interpretations]
        return d
