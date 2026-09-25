from __future__ import annotations

from .config import get_settings

# Small local deny-list for the most obvious choices. This is deliberately not
# presented as a breached-password corpus; production operators can add an
# external compromised-password check later without changing the API contract.
COMMON_PASSWORDS = {
    "password", "password123", "admin123", "qwerty123", "letmein123", "welcome123",
}


def password_policy_errors(password: str) -> list[str]:
    settings = get_settings()
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"legalább {settings.password_min_length} karakter")
    if not any(character.isupper() for character in password):
        errors.append("legalább egy nagybetű")
    if not any(character.islower() for character in password):
        errors.append("legalább egy kisbetű")
    if settings.is_production and not any(character.isdigit() for character in password):
        errors.append("legalább egy szám")
    if not any(not character.isalnum() and not character.isspace() for character in password):
        errors.append("legalább egy speciális karakter")
    if password.strip().lower() in COMMON_PASSWORDS:
        errors.append("ne legyen gyakori vagy alapértelmezett jelszó")
    return errors


def validate_password_policy(password: str) -> str:
    errors = password_policy_errors(password)
    if errors:
        raise ValueError("A jelszónak tartalmaznia kell: " + ", ".join(errors) + ".")
    return password
