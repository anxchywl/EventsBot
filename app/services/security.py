import hashlib
import hmac
import re
import secrets


# hash passwords before storage
def hash_password(password: str) -> str:
    """Hashes a password securely using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    iterations = 600000  # owasp recommendation for pbkdf2-hmac-sha256
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    # format: iterations$salt_hex$hash_hex
    return f"{iterations}${salt.hex()}${hash_bytes.hex()}"


# compare stored password hashes without exposing timing details
def verify_password(password: str, hashed: str) -> bool:
    """Verifies a password against a PBKDF2-HMAC-SHA256 hash."""
    if not hashed or "$" not in hashed:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        iterations = int(parts[0])
        salt = bytes.fromhex(parts[1])
        expected_hash = bytes.fromhex(parts[2])
        actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False


# enforce password rules shared by auth flows
def validate_password_format(password: str) -> str | None:
    """
    Validates password requirements.
    Returns an error message if invalid, or None if valid.
    """
    if not password:
        return "Password cannot be empty"
    if password.strip() != password:
        return "Password cannot contain leading or trailing spaces"
    if len(password) < 8:
        return "Password must be at least 8 characters long, silly"
    if len(password) > 128:
        return "Password must be at most 128 characters long"
    return None


# enforce public nickname rules
def validate_nickname_format(nickname: str) -> str | None:
    """
    Validates nickname requirements.
    Returns an error message if invalid, or None if valid.
    """
    if not nickname:
        return "Nickname cannot be empty"
    if nickname.strip() != nickname:
        return "Nickname cannot contain leading or trailing spaces"
    if len(nickname) < 3:
        return "Nickname must be at least 3 characters long"
    if len(nickname) > 24:
        return "Nickname must be at most 24 characters long"
    
    # block dangerous tags/html/script chars
    if re.search(r"[<>&\"'/`]", nickname):
        return "Nickname contains invalid characters"
    return None
