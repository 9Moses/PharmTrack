# conftest.py — root-level pytest anchor for the email service.
# Placing this file here alongside pytest.ini ensures pytest's rootdir is set
# to /app inside the container. Combined with `pythonpath = .` and
# `--import-mode=importlib` in pytest.ini, this makes `app.main` and
# `core.config` importable without any extra PYTHONPATH env variables.
