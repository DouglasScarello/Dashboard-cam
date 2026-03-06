import os
import base64
from Crypto.Cipher import AES
from alert_dispatcher import _maybe_encrypt

def decrypt_payload(encrypted_text: str, key_str: str) -> str:
    if not encrypted_text.startswith("[GHOST_V1]"):
        return encrypted_text
    
    try:
        data = base64.b64decode(encrypted_text.replace("[GHOST_V1]", ""))
        nonce = data[:16]
        tag = data[16:32]
        ciphertext = data[32:]
        
        key = key_str.encode("utf-8")[:32].ljust(32, b"\0")
        cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode("utf-8")
    except Exception as e:
        return f"[DECRYPT_ERROR] {e}"

if __name__ == "__main__":
    test_key = "protocol_ghost_alpha_9_test_key_32"
    test_msg = "ALVO DETECTADO: OMAR KHAN | CONFIDÊNCIA: 98%"
    
    # Simular ambiente
    os.environ["GHOST_MASTER_KEY"] = test_key
    os.environ["GHOST_ENCRYPTION_ENABLED"] = "true"
    
    print(f"Mensagem Original: {test_msg}")
    
    encrypted = _maybe_encrypt(test_msg)
    print(f"Mensagem Cifrada: {encrypted}")
    
    if encrypted.startswith("[GHOST_V1]"):
        print("✓ Cifrado com sucesso")
        
        decrypted = decrypt_payload(encrypted, test_key)
        print(f"Mensagem Decifrada: {decrypted}")
        
        if decrypted == test_msg:
            print("🚀 SUCESSO: O fluxo E2E está blindado e é 100% reversível.")
        else:
            print("❌ FALHA: A decifragem não corresponde ao original.")
    else:
        print("❌ FALHA: A mensagem não foi cifrada.")
