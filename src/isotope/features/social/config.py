"""Operations configuration for social group bots."""

from __future__ import annotations

from dataclasses import dataclass

from .messages import _string_tuple


@dataclass(frozen=True)
class SocialGroupPolicy:
    allowed_groups: tuple[str, ...] = ()
    blocked_groups: tuple[str, ...] = ()
    operator_user_ids: tuple[str, ...] = ()
    paused_groups: tuple[str, ...] = ()
    default_dry_run: bool = False

    def __post_init__(self) -> None:
        _string_tuple(self.allowed_groups, "allowed_groups")
        _string_tuple(self.blocked_groups, "blocked_groups")
        _string_tuple(self.operator_user_ids, "operator_user_ids")
        _string_tuple(self.paused_groups, "paused_groups")
        if not isinstance(self.default_dry_run, bool):
            raise ValueError("default_dry_run must be a bool")


@dataclass(frozen=True)
class SocialOperationsConfig:
    group_policy: SocialGroupPolicy = SocialGroupPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.group_policy, SocialGroupPolicy):
            raise ValueError("group_policy must be a SocialGroupPolicy")
