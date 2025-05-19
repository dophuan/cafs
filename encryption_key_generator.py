from cryptography.fernet import Fernet

def generate_encryption_key():
    """Generate a new Fernet encryption key"""
    key = Fernet.generate_key()
    print(f"Generated key (save this securely): {key.decode()}")
    return key

# Run this once to generate your key
if __name__ == "__main__":
    generate_encryption_key()