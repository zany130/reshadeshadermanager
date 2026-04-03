class RSMError(Exception):
    """Base error for RSM operations."""


class VersionResolutionError(RSMError):
    """Could not resolve a ReShade version (e.g. ``latest`` with no network and no cache)."""
