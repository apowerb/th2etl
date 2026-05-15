import os
from cryptography.fernet import Fernet
from th2agent.configs.settings import get_settings


settings = get_settings()
fernet = Fernet(settings.encrypt_key)


def encrypt_value(value: str) -> str:
    encrypted_api_key = fernet.encrypt(value.encode()).decode()
    return encrypted_api_key


def decrypt_value(encrypted_value: str) -> str:
    decrypted_api_key = fernet.decrypt(encrypted_value.encode()).decode()
    return decrypted_api_key


def encrypt_value_in_dict(input_dict: dict, values_to_encrypt: list) -> dict:
    if input_dict is None:
        return {}
    for value in values_to_encrypt:
        if value in input_dict and input_dict[value] is not None:
            input_dict[value] = encrypt_value(input_dict[value])
    return input_dict


def decrypt_value_in_dict(input_dict: dict, values_to_decrypt: list) -> dict:
    if not input_dict:
        return input_dict or {}
    for value in values_to_decrypt:
        if value in input_dict and input_dict[value] is not None:
            input_dict[value] = decrypt_value(input_dict[value])
    return input_dict


def dict_to_envvar(env_dict: dict) -> None:
    if len(env_dict.items()) == 0:
        return None
    for key, value in env_dict.items():
        os.environ[key] = str(value)