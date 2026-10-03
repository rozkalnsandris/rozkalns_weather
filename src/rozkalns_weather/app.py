from .app_core import create_app

app = create_app()

__all__ = ["app", "create_app"]
