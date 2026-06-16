# FastAPI surface for the SkinGraph pipeline.
#
# Endpoints:
#   GET    /health                       liveness probe
#   POST   /scan                         run the pipeline on an uploaded photo
#   POST   /users                        create a user profile
#   GET    /users                        list users
#   GET    /users/{user_id}              fetch one user's profile
#   PUT    /users/{user_id}              replace a user's profile
#   DELETE /users/{user_id}              delete a user
#   GET    /users/{user_id}/routine      list a user's saved routine ("shelf")
#   POST   /users/{user_id}/routine      add a product to the routine
#   DELETE /routine/{product_id}         remove a routine product
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from prometheus_fastapi_instrumentator import Instrumentator

from src.api import schemas
from src.api.service import UserNotFoundError, run_scan
from src.observability import log_tracing_status
from src.state import RoutineProduct
from src.user_store import (add_routine_product, delete_user, get_routine,
                            get_user, get_user_name, init_db, list_users,
                            remove_routine_product, save_user)

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Uploads above this size are rejected before touching disk / the VLM. Labels
# are downscaled to 2048px before inference, so a generous phone-photo ceiling.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create the users / routine_products tables if absent
    log_tracing_status()  # report whether LangSmith tracing is live
    yield


app = FastAPI(
    title="SkinGraph API",
    version="0.1.0",
    description="Extract, audit, and coach on Japanese skincare labels via a LangGraph pipeline.",
    lifespan=lifespan,
)

# Allow the browser UI (Vite dev server, or a deployed origin) to call the API.
# Override CORS_ORIGINS with a comma-separated list in production.
_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


# --- scan -------------------------------------------------------------------


@app.post("/scan", response_model=schemas.ScanResponse, tags=["scan"])
async def scan(
    image: UploadFile = File(..., description="Product label photo (front or back)."),
    image_type: Optional[str] = Form(
        None, description="Override side detection: 'front' or 'back'. Omit to auto-detect."
    ),
    user_id: Optional[str] = Form(
        None, description="Saved user id; loads their profile + routine for personalisation."
    ),
    add_to_routine: bool = Form(
        False, description="Save the scanned product to the user's routine (requires user_id)."
    ),
) -> schemas.ScanResponse:
    if image_type not in (None, "", "front", "back"):
        raise HTTPException(422, "image_type must be 'front' or 'back'.")
    if add_to_routine and not user_id:
        raise HTTPException(422, "add_to_routine requires a user_id.")

    contents = await image.read()
    if not contents:
        raise HTTPException(400, "Uploaded image is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image exceeds the 15 MB upload limit.")

    # The scanner reads the image off a path, so spool the upload to a temp file.
    # delete=False + manual unlink because Windows can't reopen an open temp file.
    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(contents)
        tmp.close()
        # app.invoke blocks (VLM calls, ~8-36s); run it off the event loop.
        return await run_in_threadpool(
            run_scan,
            image_path=tmp.name,
            image_type=(image_type or None),
            user_id=user_id,
            add_to_routine=add_to_routine,
        )
    except UserNotFoundError as exc:
        raise HTTPException(404, str(exc))
    finally:
        os.unlink(tmp.name)


# --- users ------------------------------------------------------------------


@app.post("/users", response_model=schemas.UserCreateResponse, status_code=201, tags=["users"])
def create_user(body: schemas.UserUpsertRequest) -> schemas.UserCreateResponse:
    user_id = save_user(body.profile, name=body.name)
    return schemas.UserCreateResponse(user_id=user_id)


@app.get("/users", response_model=List[schemas.UserSummary], tags=["users"])
def list_all_users() -> List[schemas.UserSummary]:
    return [schemas.UserSummary(user_id=uid, name=name) for uid, name in list_users()]


@app.get("/users/{user_id}", response_model=schemas.UserDetail, tags=["users"])
def read_user(user_id: str) -> schemas.UserDetail:
    profile = get_user(user_id)
    if profile is None:
        raise HTTPException(404, f"No user found with id: {user_id}")
    return schemas.UserDetail(user_id=user_id, name=get_user_name(user_id), profile=profile)


@app.put("/users/{user_id}", response_model=schemas.UserDetail, tags=["users"])
def replace_user(user_id: str, body: schemas.UserUpsertRequest) -> schemas.UserDetail:
    if get_user(user_id) is None:
        raise HTTPException(404, f"No user found with id: {user_id}")
    save_user(body.profile, name=body.name, user_id=user_id)
    return schemas.UserDetail(user_id=user_id, name=body.name, profile=body.profile)


@app.delete("/users/{user_id}", status_code=204, tags=["users"])
def remove_user(user_id: str) -> Response:
    if not delete_user(user_id):
        raise HTTPException(404, f"No user found with id: {user_id}")
    return Response(status_code=204)


# --- routine ("shelf") ------------------------------------------------------


@app.get("/users/{user_id}/routine", response_model=List[RoutineProduct], tags=["routine"])
def read_routine(user_id: str) -> List[RoutineProduct]:
    if get_user(user_id) is None:
        raise HTTPException(404, f"No user found with id: {user_id}")
    return get_routine(user_id)


@app.post(
    "/users/{user_id}/routine",
    response_model=schemas.RoutineProductResponse,
    status_code=201,
    tags=["routine"],
)
def add_routine(
    user_id: str, body: schemas.RoutineProductRequest
) -> schemas.RoutineProductResponse:
    if get_user(user_id) is None:
        raise HTTPException(404, f"No user found with id: {user_id}")
    product_id = add_routine_product(
        user_id, body.brand, body.product_name, body.ingredients, body.is_quasi_drug
    )
    return schemas.RoutineProductResponse(product_id=product_id)


@app.delete("/routine/{product_id}", status_code=204, tags=["routine"])
def remove_routine(product_id: str) -> Response:
    if not remove_routine_product(product_id):
        raise HTTPException(404, f"No routine product found with id: {product_id}")
    return Response(status_code=204)
