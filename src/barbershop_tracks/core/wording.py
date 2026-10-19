"""Small helpers so that messages agree in number (``1 note has``, ``3 notes have``)."""


def counted(count: int, singular: str, plural: str | None = None) -> str:
    """``1 note`` or ``3 notes``."""
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def agree(count: int, one: str, many: str) -> str:
    """``one`` when ``count`` is 1, otherwise ``many`` (for the verb or pronoun that follows)."""
    return one if count == 1 else many
