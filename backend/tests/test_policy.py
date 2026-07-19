import pytest

from emefa.domain.policy import ActionRisk, Decision, decide


def test_observation_can_run_without_confirmation():
    assert decide(ActionRisk.OBSERVE) is Decision.RUN


def test_external_communication_waits_for_confirmation():
    assert decide(ActionRisk.COMMUNICATE) is Decision.ASK


@pytest.mark.parametrize("risk", [ActionRisk.MONEY, ActionRisk.SYSTEM_CHANGE])
def test_v1_blocks_money_and_system_changes(risk):
    assert decide(risk) is Decision.BLOCK
