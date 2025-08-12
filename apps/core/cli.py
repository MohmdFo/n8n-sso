import shutil
import subprocess

import typer

cli = typer.Typer()


@cli.command()
def runserver(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = True,
):
    """
    Run the development server.
    """
    typer.echo("Starting development server...")

    # Resolve the full path of the uvicorn executable
    uvicorn_path = shutil.which("uvicorn")
    if not uvicorn_path:
        raise FileNotFoundError("Uvicorn is not installed or not found in PATH.")

    # Run uvicorn using the full executable path
    subprocess.run(
        [
            uvicorn_path,
            "apps.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--reload" if reload else "",
        ],
        check=True,
    )


@cli.command()
def runprod(
    host: str = "0.0.0.0",
    port: int = 8000,
    workers: int = 4,
):
    """
    Run the production server.
    """
    typer.echo("Starting production server...")

    # Resolve the full path of the uvicorn executable
    uvicorn_path = shutil.which("uvicorn")
    if not uvicorn_path:
        raise FileNotFoundError("Uvicorn is not installed or not found in PATH.")

    # Run uvicorn using the full executable path
    subprocess.run(
        [
            uvicorn_path,
            "apps.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--workers",
            str(workers),
        ],
        check=True,
    )
