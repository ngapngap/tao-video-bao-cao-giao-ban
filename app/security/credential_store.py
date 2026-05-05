"""Secure storage cho API keys. Ưu tiên Windows Credential Manager, fallback DPAPI."""
import json
import os
from typing import Optional

SERVICE_PREFIX = "tao-video-bao-cao"


class CredentialStore:
    def __init__(self):
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        try:
            import keyring

            keyring.get_password("test", "test")
            return "keyring"
        except Exception:
            pass
        try:
            import win32crypt

            return "dpapi"
        except ImportError:
            pass
        return "plaintext_fallback"

    def store(self, credential_id: str, secret: str) -> bool:
        if self._backend == "keyring":
            import keyring

            keyring.set_password(SERVICE_PREFIX, credential_id, secret)
            return True
        elif self._backend == "dpapi":
            return self._store_dpapi(credential_id, secret)
        else:
            return self._store_encrypted(credential_id, secret)

    def retrieve(self, credential_id: str) -> Optional[str]:
        if self._backend == "keyring":
            import keyring

            return keyring.get_password(SERVICE_PREFIX, credential_id)
        elif self._backend == "dpapi":
            return self._retrieve_dpapi(credential_id)
        else:
            return self._retrieve_encrypted(credential_id)

    def delete(self, credential_id: str) -> bool:
        if self._backend == "keyring":
            import keyring

            try:
                keyring.delete_password(SERVICE_PREFIX, credential_id)
                return True
            except Exception:
                return False
        elif self._backend == "dpapi":
            return self._delete_dpapi(credential_id)
        return self._delete_encrypted(credential_id)

    def get_backend_name(self) -> str:
        names = {
            "keyring": "Windows Credential Manager",
            "dpapi": "DPAPI (Data Protection API)",
            "plaintext_fallback": "Encrypted file (fallback)",
        }
        return names.get(self._backend, "Unknown")

    def _get_store_path(self) -> str:
        app_dir = os.path.join(os.path.expanduser("~"), ".tao-video-bao-cao")
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "credentials.enc")

    def _store_dpapi(self, credential_id: str, secret: str) -> bool:
        try:
            import win32crypt

            data = self._load_all_dpapi()
            data[credential_id] = secret
            encrypted = win32crypt.CryptProtectData(
                json.dumps(data).encode("utf-8"), None, None, None, None, 0
            )
            with open(self._get_store_path(), "wb") as f:
                f.write(encrypted)
            return True
        except Exception:
            return False

    def _retrieve_dpapi(self, credential_id: str) -> Optional[str]:
        try:
            import win32crypt

            path = self._get_store_path()
            if not os.path.exists(path):
                return None
            with open(path, "rb") as f:
                encrypted = f.read()
            decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
            data = json.loads(decrypted.decode("utf-8"))
            return data.get(credential_id)
        except Exception:
            return None

    def _delete_dpapi(self, credential_id: str) -> bool:
        try:
            data = self._load_all_dpapi()
            if credential_id in data:
                del data[credential_id]
                import win32crypt

                encrypted = win32crypt.CryptProtectData(
                    json.dumps(data).encode("utf-8"), None, None, None, None, 0
                )
                with open(self._get_store_path(), "wb") as f:
                    f.write(encrypted)
            return True
        except Exception:
            return False

    def _load_all_dpapi(self) -> dict:
        try:
            import win32crypt

            path = self._get_store_path()
            if not os.path.exists(path):
                return {}
            with open(path, "rb") as f:
                encrypted = f.read()
            decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            return {}

    def _store_encrypted(self, credential_id: str, secret: str) -> bool:
        """Fallback: XOR-based simple encryption (NOT production-grade)."""
        data = self._load_encrypted_file()
        data[credential_id] = self._xor_encrypt(secret)
        path = self._get_store_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True

    def _retrieve_encrypted(self, credential_id: str) -> Optional[str]:
        data = self._load_encrypted_file()
        encrypted = data.get(credential_id)
        if encrypted is None:
            return None
        return self._xor_decrypt(encrypted)

    def _delete_encrypted(self, credential_id: str) -> bool:
        data = self._load_encrypted_file()
        if credential_id in data:
            del data[credential_id]
            with open(self._get_store_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        return True

    def _load_encrypted_file(self) -> dict:
        path = self._get_store_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _xor_encrypt(self, text: str) -> str:
        key = "tao-video-bao-cao-key"
        return "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(text))

    def _xor_decrypt(self, text: str) -> str:
        return self._xor_encrypt(text)  # XOR is symmetric
