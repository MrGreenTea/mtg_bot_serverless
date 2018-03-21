"""Simple utility functions for use everywhere."""
import os


def get_config(name: str, default=None) -> str:
    """
    Returns the environment variable with name or default if it's not set.

    Will raise an KeyError if default is None and name is not set.
    """
    if default is None:
        try:
            return os.environ[name]
        except KeyError:
            raise KeyError(f'{name} is not set in environment') from None

    return os.environ.get(name, default)
