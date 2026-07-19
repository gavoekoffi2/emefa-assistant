"""Action-risk policy for the greenfield EMEFA V1."""

from enum import Enum


class ActionRisk(str, Enum):
    OBSERVE = "observe"
    PERSONAL_READ = "personal_read"
    LOCAL_WRITE = "local_write"
    COMMUNICATE = "communicate"
    DESTRUCTIVE = "destructive"
    MONEY = "money"
    SYSTEM_CHANGE = "system_change"


class Decision(str, Enum):
    RUN = "run"
    ASK = "ask"
    BLOCK = "block"


def decide(risk: ActionRisk) -> Decision:
    if risk in {ActionRisk.MONEY, ActionRisk.SYSTEM_CHANGE}:
        return Decision.BLOCK
    if risk in {ActionRisk.COMMUNICATE, ActionRisk.DESTRUCTIVE}:
        return Decision.ASK
    return Decision.RUN
