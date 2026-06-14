"""FastAPI service that wraps the SkinGraph LangGraph pipeline.

The HTTP layer is intentionally thin: ``service.run_scan`` builds the graph
inputs and serialises the final state, and ``main`` exposes it (plus user /
routine CRUD) over REST. Run with::

    uvicorn src.api.main:app --reload
"""
