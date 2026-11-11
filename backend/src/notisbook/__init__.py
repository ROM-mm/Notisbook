"""Notisbook: local notebook UI and Spark environment manager."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("notisbook")
except PackageNotFoundError:  # source tree without an installed distribution
    __version__ = "0+unknown"
