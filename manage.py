# manage.py

import typer
from apps.core import cli as core_cli

cli = typer.Typer()

cli.add_typer(core_cli.cli)

if __name__ == "__main__":
    cli()
