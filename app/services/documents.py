import hashlib

def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
