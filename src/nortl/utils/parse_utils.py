from typing import Optional, Tuple

__all__ = [
    'parse_int',
]


def parse_int(string: str) -> Tuple[int, Optional[int]]:
    """Parses an integer from a string.

    For numbers in binary, octal or hexadecimal representation, it infers the width.

    Arguments:
        string: Integer value as a string.

    Returns:
        Tuple of the value and inferred width.
    """

    try:
        # Parse binary, octal or hexadecimal number
        if string.startswith('0b'):
            value = int(string, 2)
            width = len(string.split('0b', maxsplit=1)[1])
        elif string.startswith('0o'):
            value = int(string, 8)
            width = len(string.split('0o', maxsplit=1)[1]) * 3
        elif string.startswith('0x'):
            value = int(string, 16)
            width = len(string.split('0x', maxsplit=1)[1]) * 4
        else:
            value = int(string)
            width = None
    except ValueError:
        raise ValueError(f"Unable to create Const from '{string}', failed to convert it to integer.")

    return value, width
