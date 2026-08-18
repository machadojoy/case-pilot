"""Model registry: imports every table model so it registers in SQLModel.metadata.

Both Alembic autogenerate (`alembic/env.py`) and the test schema setup
(`tests/conftest.py`) import this module. A table model that is NOT imported here
is invisible to them — autogenerate will silently skip it and no migration is made.

>>> When you add a new table model, import it below (and add it to __all__). <<<
"""

from app.organizations.models import Organization

__all__ = ["Organization"]
