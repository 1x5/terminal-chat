import pytest
from src.signatures import MessageSigner, SignatureError, SignatureVerificationError

@pytest.fixture
def signer():
    return MessageSigner()

def test_signature_creation(signer):
    """Тест создания подписи"""
    message = "Тестовое сообщение"
    signature, public_key = signer.sign_message(message)
    
    assert signature is not None
    assert public_key is not None
    assert len(signature) > 0
    assert len(public_key) > 0

def test_signature_verification(signer):
    """Тест проверки подписи"""
    message = "Тестовое сообщение"
    signature, public_key = signer.sign_message(message)
    
    assert MessageSigner.verify_signature(message, signature, public_key)

def test_invalid_signature(signer):
    """Тест с неверной подписью"""
    message = "Тестовое сообщение"
    signature, public_key = signer.sign_message(message)
    
    # Меняем подпись
    invalid_signature = signature[:-1] + ('1' if signature[-1] == '0' else '0')
    
    with pytest.raises(SignatureVerificationError):
        MessageSigner.verify_signature(message, invalid_signature, public_key)

def test_invalid_message(signer):
    """Тест с измененным сообщением"""
    message = "Тестовое сообщение"
    signature, public_key = signer.sign_message(message)
    
    # Меняем сообщение
    modified_message = message + "!"
    
    with pytest.raises(SignatureVerificationError):
        MessageSigner.verify_signature(modified_message, signature, public_key)

def test_json_message_signing(signer):
    """Тест подписи JSON сообщения"""
    data = {
        "type": "chat",
        "content": "Привет!",
        "sender": "alice"
    }
    
    signed_data = signer.sign_json_message(data)
    
    assert "signature" in signed_data
    assert "public_key" in signed_data
    assert "timestamp" in signed_data
    assert MessageSigner.verify_json_message(signed_data)

def test_json_message_verification(signer):
    """Тест проверки JSON сообщения"""
    data = {
        "type": "chat",
        "content": "Привет!",
        "sender": "alice"
    }
    
    signed_data = signer.sign_json_message(data)
    
    # Меняем данные
    signed_data["content"] = "Пока!"
    
    with pytest.raises(SignatureVerificationError):
        MessageSigner.verify_json_message(signed_data) 