"""Fernet symmetric encryption for at-rest data.

OSS posture: app-layer encryption is OFF by default. Single-tenant
self-hosted deployments rely on full-disk encryption (LUKS, FileVault,
BitLocker) for the same threat model — see docs/encryption.md.

To enable Fernet, set ANYLEGAL_ENCRYPTION_KEY. Procurement deployments
that want to refuse to start without a key can additionally set
ANYLEGAL_REQUIRE_ENCRYPTION=true (opt in to fail-loud).
"""

import os
import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_KEY = os.environ.get('ANYLEGAL_ENCRYPTION_KEY')
REQUIRE_ENCRYPTION = os.environ.get('ANYLEGAL_REQUIRE_ENCRYPTION', '').lower() == 'true'

ENCRYPTION_AVAILABLE = False
_fernet: Optional[Fernet] = None


class EncryptionConfigError(RuntimeError):
    """Raised when ANYLEGAL_ENCRYPTION_KEY is invalid, or absent while
    ANYLEGAL_REQUIRE_ENCRYPTION=true."""


def _initialize_encryption():
    """Initialize the Fernet instance. Raises on a present-but-invalid key,
    or on an absent key when ANYLEGAL_REQUIRE_ENCRYPTION=true."""
    global ENCRYPTION_AVAILABLE, _fernet

    if not ENCRYPTION_KEY:
        if REQUIRE_ENCRYPTION:
            raise EncryptionConfigError(
                "ANYLEGAL_REQUIRE_ENCRYPTION=true but ANYLEGAL_ENCRYPTION_KEY is not set. "
                "Generate a key with `python -c \"from anylegal_oss.utils.encryption "
                "import generate_encryption_key; print(generate_encryption_key())\"`."
            )
        logger.warning(
            "ANYLEGAL_ENCRYPTION_KEY not set: data will be stored as plaintext "
            "(PLAIN: prefix). Set the key to enable Fernet at-rest encryption, or "
            "set ANYLEGAL_REQUIRE_ENCRYPTION=true to refuse to start without a key."
        )
        return

    key_bytes = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
    try:
        _fernet = Fernet(key_bytes)
    except (ValueError, TypeError) as e:
        raise EncryptionConfigError(
            f"ANYLEGAL_ENCRYPTION_KEY is set but invalid (Fernet rejected it): {e}. "
            f"Generate a fresh key with `python -c \"from anylegal_oss.utils.encryption "
            f"import generate_encryption_key; print(generate_encryption_key())\"`."
        ) from e
    ENCRYPTION_AVAILABLE = True
    logger.info("Encryption initialized")


_initialize_encryption()


def encrypt_text(plaintext: str) -> str:
    """Encrypt a string with the configured Fernet key.

    Returns:
        f"ENC:<base64 ciphertext>" when a key is configured;
        f"PLAIN:<plaintext>" otherwise.
    """
    if not plaintext:
        return plaintext

    if not ENCRYPTION_AVAILABLE or not _fernet:
        return f"PLAIN:{plaintext}"

    encrypted_bytes = _fernet.encrypt(plaintext.encode('utf-8'))
    return f"ENC:{encrypted_bytes.decode('utf-8')}"

def decrypt_text(ciphertext: str) -> str:
    """
    Decrypt an encrypted string.

    Handles both encrypted data (prefixed with ENC:) and
    plaintext data (prefixed with PLAIN: or no prefix for legacy data).

    Args:
        ciphertext: The encrypted or marked text

    Returns:
        Decrypted plaintext
    """
    if not ciphertext:
        return ciphertext

    if ciphertext.startswith('PLAIN:'):
        return ciphertext[6:]                        

    if not ciphertext.startswith('ENC:'):
        return ciphertext

    if not ENCRYPTION_AVAILABLE or not _fernet:
        logger.warning("Cannot decrypt - encryption not available")
        return "[Encrypted data - key not available]"

    try:
        encrypted_bytes = ciphertext[4:].encode('utf-8')                      
        decrypted_bytes = _fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.error("Decryption failed - invalid token (wrong key?)")
        return "[Decryption failed]"
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return "[Decryption error]"

def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt binary data with the configured Fernet key.

    Returns the data unchanged when no key is configured.
    """
    if not data:
        return data

    if not ENCRYPTION_AVAILABLE or not _fernet:
        return data

    return _fernet.encrypt(data)

def decrypt_bytes(data: bytes) -> bytes:
    """
    Decrypt encrypted binary data.

    Used for DOCX file retrieval in the Hybrid DOCX Architecture.

    Args:
        data: Encrypted binary data

    Returns:
        Decrypted bytes (or original if decryption fails)
    """
    if not data:
        return data

    if not ENCRYPTION_AVAILABLE or not _fernet:

        return data

    try:
        return _fernet.decrypt(data)
    except InvalidToken:

        logger.debug("Data appears to be unencrypted, returning as-is")
        return data
    except Exception as e:
        logger.error(f"Binary decryption error: {e}")
        return data

def encrypt_dict(data: dict, fields_to_encrypt: list) -> dict:
    """
    Encrypt specific fields in a dictionary.

    Args:
        data: Dictionary containing data
        fields_to_encrypt: List of field names to encrypt

    Returns:
        Dictionary with specified fields encrypted
    """
    result = data.copy()
    for field in fields_to_encrypt:
        if field in result and result[field]:
            result[field] = encrypt_text(str(result[field]))
    return result

def decrypt_dict(data: dict, fields_to_decrypt: list) -> dict:
    """
    Decrypt specific fields in a dictionary.

    Args:
        data: Dictionary containing encrypted data
        fields_to_decrypt: List of field names to decrypt

    Returns:
        Dictionary with specified fields decrypted
    """
    result = data.copy()
    for field in fields_to_decrypt:
        if field in result and result[field]:
            result[field] = decrypt_text(str(result[field]))
    return result

def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Use this to create a key for the ANYLEGAL_ENCRYPTION_KEY env variable:
        python -c "from anylegal_oss.utils.encryption import generate_encryption_key; print(generate_encryption_key())"

    Returns:
        Base64-encoded Fernet key
    """
    return Fernet.generate_key().decode('utf-8')

def derive_key_from_password(password: str, salt: bytes = None) -> tuple:
    """
    Derive an encryption key from a user's password.

    This can be used for user-specific encryption where only
    the user can decrypt their own data.

    Args:
        password: User's password
        salt: Optional salt bytes (generated if not provided)

    Returns:
        Tuple of (key, salt) for storage
    """
    if salt is None:
        salt = os.urandom(16)

    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        100000,              
        dklen=32
    )

    fernet_key = base64.urlsafe_b64encode(key)

    return fernet_key.decode('utf-8'), base64.b64encode(salt).decode('utf-8')

def get_encryption_status() -> dict:
    """Return a public-safe encryption status. Does not leak any key bytes."""
    return {
        "available": ENCRYPTION_AVAILABLE,
        "key_configured": bool(ENCRYPTION_KEY),
        "require_encryption": REQUIRE_ENCRYPTION,
    }
