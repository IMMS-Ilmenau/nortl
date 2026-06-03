"""Checksum calculation."""

import json
from hashlib import sha256

__all__ = [
    'create_sha256sum',
]


def create_sha256sum(*objects: object) -> str:
    """Create SHA256 checksum from one or more objects.

    Arguments:
        objects: One or more objects that are included in the checksum. The objects must support serialization as JSON string.

    Returns:
        SHA256 checksum as hexdigest.
    """
    hash = sha256()
    for object in objects:
        hash.update(json.dumps(object, ensure_ascii=True, sort_keys=True).encode('ascii'))
    return hash.hexdigest()
