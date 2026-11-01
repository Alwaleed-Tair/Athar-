from fastapi import APIRouter, Depends, Query

from .. import relations
from ..database import get_conn
from ..deps import get_current_user

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=200),
    case_id: int | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Keyword search over case names, evidence names/descriptions, extracted
    text and conversation messages. Results are ALWAYS limited to cases the
    caller is a member of; a case_id the caller cannot open simply yields no
    results (indistinguishable from a case with no matches)."""
    with get_conn() as conn:
        return relations.search_all(conn, user["id"], q, case_id=case_id)


@router.get("/search/semantic")
def semantic_search(
    q: str = Query(min_length=2, max_length=300),
    case_id: int | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Search by meaning (embeddings). Disabled unless an embeddings provider is
    configured; limited to the caller's own cases like every other search."""
    from .. import embeddings
    with get_conn() as conn:
        return embeddings.search(conn, user["id"], q, case_id=case_id)
