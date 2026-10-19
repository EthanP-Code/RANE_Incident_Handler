"""Start RANE locally from the repository root."""
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root / "backend"))
    load_dotenv(root / ".env")
    load_dotenv(root / "backend" / ".env")
    uvicorn.run("rane_api.main:app", host="127.0.0.1", port=8000)
