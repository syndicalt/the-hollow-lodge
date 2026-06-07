import typer

from hollow_lodge import __version__


app = typer.Typer(
    name="hollow-lodge",
    help="The Hollow Lodge CLI.",
    no_args_is_help=True,
)


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed Hollow Lodge version.",
    ),
) -> None:
    """The Hollow Lodge command-line client."""
    if version:
        typer.echo(f"The Hollow Lodge {__version__}")
        raise typer.Exit()


def main() -> None:
    app()


if __name__ == "__main__":
    main()

