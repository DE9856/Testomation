import pytest

from testomation.cli import COMMANDS, main


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage: testomation" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["run", "review", "approve", "explore"])
def test_stub_commands_report_not_implemented(command, capsys):
    assert main([command]) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_import_requires_a_report():
    with pytest.raises(SystemExit):
        main(["import"])


def test_every_command_names_its_phase():
    assert all(phase for _, phase in COMMANDS.values())
