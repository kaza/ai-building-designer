"""ArchiCAD Builder CLI."""

import typer

app = typer.Typer(
    name="archicad-builder",
    help="Collaborative building design → IFC export for ArchiCAD",
)


@app.command()
def version() -> None:
    """Show version."""
    from archicad_builder import __version__

    typer.echo(f"archicad-builder v{__version__}")


if __name__ == "__main__":
    app()
