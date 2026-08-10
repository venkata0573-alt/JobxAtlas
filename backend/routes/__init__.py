"""Route modules for Job Atlas backend.

Each module imports the shared `api` APIRouter from `deps` and registers its
endpoints onto it. `server.py` triggers registration by importing these modules
at the module level, then includes `api` into the FastAPI app once.
"""
