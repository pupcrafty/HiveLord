#!/usr/bin/env python3
"""Standalone script to run the HiveLord web UI."""
import sys
from app.ui.server import run_server

if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            print("Usage: python run_ui.py [port]")
            sys.exit(1)
    
    print(f"Starting HiveLord Dashboard on http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop")
    run_server(host="127.0.0.1", port=port, debug=False)

