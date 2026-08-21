from typer.testing import CliRunner


def test_web_command_exposes_the_guided_local_studio() -> None:
    from autoclip.cli import app

    result = CliRunner().invoke(app, ["web", "--help"])

    assert result.exit_code == 0
    assert "packaged local Studio" in result.output
