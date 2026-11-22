"""
Sentinel AI — Phase 13: investigation API.

Endpoints
---------
GET  /health                              liveness + store / investigator readiness (public)
POST /api/v1/auth/login                   sign in (sets an HttpOnly session cookie)
POST /api/v1/auth/logout                  sign out
GET  /api/v1/auth/me                      current analyst
POST /api/v1/auth/password                change own password
POST /api/v1/alerts                       ingest an alert → case (202; ?wait=true blocks until investigated)
GET  /api/v1/cases                        case queue (priority order; ?status= &action= &limit= &offset=)
GET  /api/v1/cases/{case_id}              full case: transaction, agent outputs, report, validation, audit
GET  /api/v1/cases/{case_id}/report       presented report (JSON, or ?format=markdown)
GET  /api/v1/cases/{case_id}/audit        audit trail
GET  /api/v1/cases/{case_id}/network      account network from the stored Agent 3 findings
POST /api/v1/cases/{case_id}/decision     analyst decision (appended; revisions kept)

Every /api/v1 endpoint except login needs a signed-in analyst (session
cookie). Alert ingestion alternatively accepts ``X-API-Key`` when
``SENTINEL_INGEST_API_KEY`` is set (server-side alert sources).

``create_app`` has no side effects at import, so tests can build an app with a
temporary store and fake agents. ``src/api/main.py`` is the server entry point.
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .auth import (
    COOKIE_NAME, AuthError, AuthService, AuthStore, LoginLocked, LoginRequest, PasswordChangeRequest, PublicUser,
    User, auth_store_from_env,
)
from .case_schema import (
    PROTOTYPE_NOTICE, AlertAccepted, AlertRequest, AuditEvent, CaseList, CaseListItem, CaseRecord, CaseStatus,
    DecisionRequest,
)
from .case_store import CaseStore, CaseStoreError, case_store_from_env
from .service import CaseService, Conflict, FeedUnavailable, NotFound, QueueFull

API_VERSION = "1.0.0"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000"


def _cors_origins() -> list[str]:
    raw = os.environ.get("SENTINEL_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError("SENTINEL_CORS_ORIGINS must list origins explicitly; '*' is not allowed.")
    return origins


def _store_errors() -> tuple[type[BaseException], ...]:
    errs: list[type[BaseException]] = [CaseStoreError]
    try:
        from pymongo.errors import PyMongoError

        errs.append(PyMongoError)
    except ImportError:  # pragma: no cover
        pass
    return tuple(errs)


def create_app(
    store: Optional[CaseStore] = None,
    investigator_factory: Optional[Callable[[], Any]] = None,
    feed_lookup: Optional[Callable[[str], Optional[dict]]] = None,
    ingest_api_key: Optional[str] = None,
    alert_wait_seconds: Optional[float] = None,
    auth_store: Optional[AuthStore] = None,
    cookie_secure: Optional[bool] = None,
) -> FastAPI:
    ingest_key = ingest_api_key if ingest_api_key is not None else os.environ.get("SENTINEL_INGEST_API_KEY", "")
    secure = cookie_secure if cookie_secure is not None else (
        os.environ.get("SENTINEL_COOKIE_SECURE", "true").strip().lower() != "false")
    wait_seconds = alert_wait_seconds if alert_wait_seconds is not None else float(
        os.environ.get("SENTINEL_ALERT_WAIT_SECONDS", "180"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        kwargs: dict[str, Any] = {"max_pending": int(os.environ.get("SENTINEL_MAX_PENDING_CASES", "50"))}
        if investigator_factory is not None:
            kwargs["investigator_factory"] = investigator_factory
        if feed_lookup is not None:
            kwargs["feed_lookup"] = feed_lookup
        service = CaseService(store or case_store_from_env(), **kwargs)
        service.start()
        app.state.service = service
        app.state.auth = AuthService(auth_store or auth_store_from_env())
        yield
        service.shutdown()

    app = FastAPI(
        title="Sentinel AI — Investigation API",
        description="Alert ingestion, investigation cases and analyst decisions. " + PROTOTYPE_NOTICE,
        version=API_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])

    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def _conflict(_: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(QueueFull)
    async def _full(_: Request, exc: QueueFull):
        return JSONResponse(status_code=429, content={"detail": "Investigation queue is full; retry later."},
                            headers={"Retry-After": "60"})

    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(LoginLocked)
    async def _locked(_: Request, exc: LoginLocked):
        return JSONResponse(status_code=429, content={"detail": str(exc)},
                            headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(FeedUnavailable)
    async def _feed(_: Request, exc: FeedUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    for err in _store_errors():
        @app.exception_handler(err)
        async def _store(_: Request, exc: Exception):  # message not exposed (may contain hosts)
            return JSONResponse(status_code=503, content={"detail": "Case store unavailable."})

    def service(request: Request) -> CaseService:
        return request.app.state.service

    def auth(request: Request) -> AuthService:
        return request.app.state.auth

    def current(request: Request, session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)):
        return request.app.state.auth.authenticate(session_token)

    def analyst(cur=Depends(current)) -> User:
        return cur[0]

    def alert_submitter(request: Request, x_api_key: Optional[str] = Header(default=None),
                        session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)) -> str:
        """A signed-in analyst, or a server-side source holding the ingest key."""
        if x_api_key is not None:
            if ingest_key and hmac.compare_digest(x_api_key, ingest_key):
                return "ingest-api-key"
            raise HTTPException(status_code=401, detail="Invalid X-API-Key.")
        return request.app.state.auth.authenticate(session_token)[0].username

    # ------------------------------------------------------------------
    @app.post("/api/v1/auth/login", response_model=PublicUser)
    def login(body: LoginRequest, response: Response, svc: AuthService = Depends(auth)):
        token, user, session = svc.login(body)
        response.set_cookie(
            COOKIE_NAME, token, httponly=True, secure=secure, samesite="lax", path="/",
            max_age=int((session.absolute_expires_at_utc - session.created_at_utc).total_seconds())
            if body.remember else None,
        )
        return PublicUser(username=user.username, display_name=user.display_name)

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(response: Response, svc: AuthService = Depends(auth),
               session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)):
        svc.logout(session_token)
        response.delete_cookie(COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="lax")
        response.status_code = 204
        return response

    @app.get("/api/v1/auth/me", response_model=PublicUser)
    def me(user: User = Depends(analyst)):
        return PublicUser(username=user.username, display_name=user.display_name)

    @app.post("/api/v1/auth/password", status_code=204)
    def change_password(body: PasswordChangeRequest, cur=Depends(current), svc: AuthService = Depends(auth)):
        try:
            svc.change_password(cur[0], cur[1], body)
        except ValueError as exc:  # password policy
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return Response(status_code=204)

    # ------------------------------------------------------------------
    @app.get("/health")
    def health(svc: CaseService = Depends(service)) -> dict:
        try:
            store_ok = bool(svc.store.ping())
        except Exception:  # noqa: BLE001
            store_ok = False
        return {
            "status": "ok" if store_ok else "degraded",
            "api_version": API_VERSION,
            "case_store": svc.store.backend_name,
            "case_store_ok": store_ok,
            "investigator_ready": svc.investigator_ready,
            "investigator_error": svc.investigator_error,
            "pending_investigations": svc.pending,
            "prototype_notice": PROTOTYPE_NOTICE,
        }

    @app.post("/api/v1/alerts", response_model=AlertAccepted, status_code=202)
    def ingest_alert(alert: AlertRequest, wait: bool = Query(False, description="Block until the investigation ends."),
                     svc: CaseService = Depends(service), submitted_by: str = Depends(alert_submitter)):
        accepted, fut = svc.ingest(alert, submitted_by=submitted_by)
        if accepted.duplicate:
            return JSONResponse(status_code=200, content=accepted.model_dump(mode="json"))
        if wait and fut is not None:
            try:
                fut.result(timeout=wait_seconds)
            except TimeoutError:
                pass  # still running: report current status
            rec = svc.get(accepted.case_id)
            done = AlertAccepted(case_id=rec.case_id, status=rec.status, duplicate=False, summary=rec.summary)
            return JSONResponse(status_code=200 if rec.status != CaseStatus.RECEIVED else 202,
                                content=done.model_dump(mode="json"))
        return accepted

    @app.get("/api/v1/cases", response_model=CaseList)
    def list_cases(status: Optional[CaseStatus] = None, action: Optional[str] = Query(None, max_length=32),
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   svc: CaseService = Depends(service), _: User = Depends(analyst)):
        docs, total = svc.store.list(status=status, action=action, limit=limit, offset=offset)
        items = []
        for d in docs:
            tx = d.get("transaction") or {}
            items.append(CaseListItem(
                case_id=d["case_id"], status=d["status"], created_at_utc=d["created_at_utc"],
                updated_at_utc=d["updated_at_utc"], transaction_id=tx.get("raw_record_id"),
                amount=None if tx.get("amount") is None else str(tx["amount"]), currency=tx.get("currency"),
                alert=d["alert"], summary=d.get("summary") or {},
                analyst_action=(d.get("analyst_decision") or {}).get("action"),
            ))
        return CaseList(total=total, limit=limit, offset=offset, items=items)

    @app.get("/api/v1/cases/{case_id}", response_model=CaseRecord)
    def get_case(case_id: str, svc: CaseService = Depends(service), _: User = Depends(analyst)):
        return svc.get(case_id)

    @app.get("/api/v1/cases/{case_id}/report")
    def get_report(case_id: str, format: str = Query("json", pattern="^(json|markdown)$"),
                   svc: CaseService = Depends(service), _: User = Depends(analyst)):
        rec = svc.get(case_id)
        inv = rec.investigation or {}
        if not inv.get("agent5_output"):
            raise NotFound(f"Case {case_id} has no report"
                           + (f" ({inv.get('halt_reason')})" if inv.get("halt_reason") else f" (status {rec.status.value})."))
        if format == "json":
            return {"case_id": case_id, "report": inv["agent5_output"], "validation": inv.get("validation_output"),
                    "rejected_reports": inv.get("rejected_reports") or [], "prototype_notice": PROTOTYPE_NOTICE}
        from ..agents.agent5 import render_markdown
        from ..agents.agent5.report_schema import Agent5Output
        from ..agents.validator.schema import ValidationOutput

        report = Agent5Output.model_validate(inv["agent5_output"])
        validation = ValidationOutput.model_validate(inv["validation_output"]) if inv.get("validation_output") else None
        return PlainTextResponse(render_markdown(report, validation=validation), media_type="text/markdown")

    @app.get("/api/v1/cases/{case_id}/network")
    def get_network(case_id: str, svc: CaseService = Depends(service), _: User = Depends(analyst)):
        from .network_view import build_network_view

        view = build_network_view(svc.get(case_id))
        if view is None:
            raise NotFound(f"Case {case_id} has no network analysis yet.")
        return view

    @app.get("/api/v1/cases/{case_id}/audit", response_model=list[AuditEvent])
    def get_audit(case_id: str, svc: CaseService = Depends(service), _: User = Depends(analyst)):
        return svc.get(case_id).audit_trail

    @app.post("/api/v1/cases/{case_id}/decision", response_model=CaseRecord)
    def decide(case_id: str, decision: DecisionRequest, svc: CaseService = Depends(service),
               user: User = Depends(analyst)):
        return svc.decide(case_id, decision, analyst_id=user.username, analyst_name=user.display_name)

    return app


__all__ = ["create_app", "API_VERSION"]
