import os
import pytest
from pathlib import Path
from src.e2e_encryption import E2EEncryption

@pytest.fixture
def temp_key_dir(tmp_path):
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    return key_dir

@pytest.fixture
def encryption(temp_key_dir):
    e2e = E2EEncryption(temp_key_dir)
    e2e.generate_keys()
    return e2e

def test_key_generation(temp_key_dir):
    e2e = E2EEncryption(temp_key_dir)
    e2e.generate_keys()
    
    assert (temp_key_dir / "private_key.pem").exists()
    assert (temp_key_dir / "public_key.pem").exists()

def test_key_loading(temp_key_dir, encryption):
    # Create new instance and load existing keys
    e2e = E2EEncryption(temp_key_dir)
    e2e.load_keys()
    
    assert e2e.private_key is not None
    assert e2e.public_key is not None

def test_peer_key_management(encryption):
    peer_id = "test_peer"
    peer_key = encryption.get_public_key_pem()
    
    # Add peer key
    encryption.add_peer_key(peer_id, peer_key)
    
    # Verify key retrieval
    retrieved_key = encryption.get_peer_key(peer_id)
    assert retrieved_key is not None

def test_message_encryption_decryption(temp_key_dir):
    # Create two E2E instances
    alice = E2EEncryption(temp_key_dir / "alice")
    bob = E2EEncryption(temp_key_dir / "bob")
    
    alice.generate_keys()
    bob.generate_keys()
    
    # Exchange public keys
    alice.add_peer_key("bob", bob.get_public_key_pem())
    bob.add_peer_key("alice", alice.get_public_key_pem())
    
    # Test message encryption/decryption
    original_message = "Hello, Bob!"
    encrypted = alice.encrypt_message("bob", original_message)
    decrypted = bob.decrypt_message(encrypted)
    
    assert decrypted == original_message

def test_invalid_peer(encryption):
    with pytest.raises(KeyError):
        encryption.get_peer_key("nonexistent_peer")

def test_invalid_key_format(encryption):
    with pytest.raises(ValueError):
        encryption.add_peer_key("test_peer", b"invalid key data") 