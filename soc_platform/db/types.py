"""Column helpers for string-valued enums and membership checks."""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint, Enum as SAEnum


def enum_column(enum_cls: type[enum.Enum], *, length: int = 32) -> SAEnum:
    """Persist enum values as strings. Membership is enforced by an explicit check."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


def enum_check(column: str, enum_cls: type[enum.Enum], name: str) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=name)
