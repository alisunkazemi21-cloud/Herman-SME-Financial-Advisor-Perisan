from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def exact_decimal(value: Any) -> Decimal:
    if isinstance(value, (float, bool)):
        raise ValueError("مبلغ باید رشته یا عدد صحیح باشد؛ اعشار شناور مجاز نیست")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("عدد باید متناهی باشد")
    return result


Money = Annotated[Decimal, BeforeValidator(exact_decimal)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Evidence(Model):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_file: str = Field(min_length=1)
    locator: str = Field(min_length=1)

    @classmethod
    def from_file(cls, path: str | Path, locator: str = "فایل کامل") -> Evidence:
        file = Path(path).resolve()
        return cls(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                   source_file=str(file), locator=locator)

    def verify(self) -> None:
        if hashlib.sha256(Path(self.source_file).read_bytes()).hexdigest() != self.sha256:
            raise ValueError("فایل شاهد تغییر کرده است")


class Fact(Model):
    value: Money
    evidence: Evidence
