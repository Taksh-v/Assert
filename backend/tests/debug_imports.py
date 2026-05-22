print("1. Importing sys...")
import sys
print("2. Importing os...")
import os
print("3. Importing sqlalchemy...")
import sqlalchemy
print("4. Importing pydantic...")
import pydantic
print("5. Importing jose...")
from jose import jwt
from unittest.mock import MagicMock
sys.modules["passlib"] = MagicMock()
sys.modules["passlib.context"] = MagicMock()
print("6. Mocking passlib context...")
from passlib.context import CryptContext
print("7. Importing bcrypt...")
import bcrypt
print("8. Importing qdrant_client...")
import qdrant_client
print("9. Importing sentence_transformers...")
import sentence_transformers
print("10. Importing all completed successfully!")
