"""Adapter over text2num. The only module that touches the cardinal backend."""

from functools import lru_cache

from text_to_num import text2num


@lru_cache(maxsize=4096)
def cardinal_value(words: tuple[str, ...]) -> int | None:
    """Value of a complete cardinal phrase, or None if the backend rejects it.

    Only ValueError means "not a cardinal". Anything else is an operational
    failure and propagates.
    """
    try:
        return text2num(" ".join(words), "en")
    except ValueError:
        return None
