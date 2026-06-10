import pytest
import json
from backend.core.security import encrypt_config, decrypt_config, _get_encryption_secret, _get_fernet_for_secret
import backend.core.security

def test_connector_encryption_default(monkeypatch):
    """Test encrypting and decrypting with the default placeholder secret."""
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "change-me-to-a-random-64-char-string")
    monkeypatch.setattr(backend.core.security.settings, "supabase_jwt_secret", None)
    
    config = {"token": "my-secret-token", "channels": ["general"]}
    encrypted = encrypt_config(config)
    
    assert isinstance(encrypted, str)
    assert encrypted != ""
    
    decrypted = decrypt_config(encrypted)
    assert decrypted == config

def test_connector_encryption_custom_key(monkeypatch):
    """Test encrypting and decrypting with a custom app_secret_key."""
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "my-custom-super-secret-key-123456")
    monkeypatch.setattr(backend.core.security.settings, "supabase_jwt_secret", None)
    
    config = {"token": "custom-token"}
    encrypted = encrypt_config(config)
    
    decrypted = decrypt_config(encrypted)
    assert decrypted == config

def test_connector_decryption_fallback_to_default(monkeypatch):
    """Test that a config encrypted with the default key can still be decrypted
    after changing the app_secret_key to a custom one.
    """
    # 1. Encrypt with default
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "change-me-to-a-random-64-char-string")
    monkeypatch.setattr(backend.core.security.settings, "supabase_jwt_secret", None)
    config = {"token": "original-token"}
    encrypted = encrypt_config(config)
    
    # 2. Change key to a custom one
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "new-custom-key-rotated")
    
    # 3. Decrypt should still succeed via fallback
    decrypted = decrypt_config(encrypted)
    assert decrypted == config

def test_connector_decryption_fallback_to_supabase_secret(monkeypatch):
    """Test encrypting with supabase_jwt_secret (when app_secret_key is default)
    and then rotating keys, verifying fallback decryption works.
    """
    # 1. Setup default app_secret_key and custom supabase_jwt_secret
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "change-me-to-a-random-64-char-string")
    monkeypatch.setattr(backend.core.security.settings, "supabase_jwt_secret", "supa-jwt-secret-abc-123")
    
    # Primary key should now be supabase_jwt_secret
    assert _get_encryption_secret() == "supa-jwt-secret-abc-123"
    
    config = {"token": "supa-token"}
    encrypted = encrypt_config(config)
    
    # 2. Rotate to custom app_secret_key, but keep supabase_jwt_secret the same
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "another-new-app-key")
    
    # 3. Decrypt should still succeed by falling back to the supa key which is in the secrets list
    decrypted = decrypt_config(encrypted)
    assert decrypted == config

def test_connector_decryption_invalid_fails(monkeypatch):
    """Test that invalid or corrupt strings throw ValueError."""
    monkeypatch.setattr(backend.core.security.settings, "app_secret_key", "some-key")
    
    with pytest.raises(ValueError) as excinfo:
        decrypt_config("gAAAAABinvalidstring")
    assert "Failed to decrypt connector configuration" in str(excinfo.value)
