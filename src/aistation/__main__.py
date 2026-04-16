"""Allow ``python -m aistation`` as an alternative to the ``aistation`` script."""
from .cli.main import app

if __name__ == "__main__":
    app()
