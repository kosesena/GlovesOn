"""
The GlovesOn gateway package.

The .env file is read here — before any of the submodules is imported.
Previously main.py called load_dotenv() AFTER its import lines, so every
variable read at module scope (DATABASE_URL in store, SAP_BASE_URL in
sap_client) saw an empty value. SAP_BASE_URL looking empty was a silent and
expensive failure: it meant pointing at a real tenant and quietly writing
to the mock anyway.
"""

from dotenv import load_dotenv

load_dotenv()
