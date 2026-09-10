"""
Root CLI entrypoint — delegates execution to app.scripts.push_to_firebase.
"""

from app.scripts.push_to_firebase import main

if __name__ == "__main__":
    main()
