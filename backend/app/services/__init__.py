"""Business logic for the CRUD resources. Routers stay thin and call these functions.

Each service function takes an AsyncSession and plain values, so the same code is used by
routers, background pipelines, the demo seed and tests.
"""
