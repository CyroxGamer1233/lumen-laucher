"""PyInstaller entry point: absolute imports only (relative imports fail in a frozen script)."""
from lumen.ui.app import main

raise SystemExit(main())
