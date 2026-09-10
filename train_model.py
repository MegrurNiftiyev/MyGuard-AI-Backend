"""
Root CLI entrypoint — delegates execution to app.scripts.train_model.
"""

from app.scripts.train_model import main

if __name__ == "__main__":
    main()
