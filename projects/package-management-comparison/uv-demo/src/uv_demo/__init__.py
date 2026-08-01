"""Runnable entry point for the uv package-management demo."""

import httpx


def main() -> None:
    """Print the installed HTTPX version."""
    print(httpx.__version__)
