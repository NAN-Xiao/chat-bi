"""Consistent database snapshots for semantic and SQL permission decisions."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.crud.metadata_permission import (
    MetadataPermissionService,
    MetadataPermissionValidationError,
)
from apps.datasource.crud.permission import get_applicable_row_permission_constraints
from apps.datasource.crud.permission_scope import (
    PermissionScopeSnapshot,
    PermissionScopeUnavailableError,
    SemanticScopeCoordinate,
    load_semantic_scope_epochs,
    permission_cache_key,
    stable_permission_hash,
)
from apps.datasource.crud.permission_scope_objects import (
    PermissionObjectProjectionError,
    build_allowed_object_keys,
    row_constraints_hash,
)
from apps.datasource.models.datasource import (
    CoreDatasource,
    CoreDatasourceUser,
)
from apps.datasource.models.semantic_scope import SemanticScopeType
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import SYSTEM_ADMIN_ROLES, normalize_system_role
from apps.system.models.tenant import TenantUserModel
from apps.system.models.user import UserModel


class PermissionScopeReadError(RuntimeError):
    pass


class PermissionSnapshotCache(Protocol):
    def get(self, key: str) -> PermissionScopeSnapshot | None: ...

    def set(self, key: str, snapshot: PermissionScopeSnapshot) -> None: ...


@dataclass(frozen=True)
class PermissionAuthorityState:
    tenant_id: int
    user_id: int
    datasource_id: int
    system_role: str
    user_status: int
    membership_role: str
    membership_status: int
    datasource_access_recorded: bool
    datasource_role: str | None
    bound_datasource_id: int
    schema_hash: str
    epochs: tuple[tuple[str, int, int | None, int | None, int], ...]


def _authority_version(state: PermissionAuthorityState) -> str:
    return stable_permission_hash(
        {
            "tenant_id": state.tenant_id,
            "user_id": state.user_id,
            "datasource_id": state.datasource_id,
            "system_role": state.system_role,
            "user_status": state.user_status,
            "membership_role": state.membership_role,
            "membership_status": state.membership_status,
            "datasource_access_recorded": state.datasource_access_recorded,
            "datasource_role": state.datasource_role,
            "bound_datasource_id": state.bound_datasource_id,
            "schema_hash": state.schema_hash,
            "epochs": state.epochs,
        }
    )


class PermissionScopeRepository:
    def __init__(self, engine, *, cache: PermissionSnapshotCache | None = None):
        self.engine = engine
        self.cache = cache

    def build_snapshot(
        self,
        *,
        tenant_id: int,
        user_id: int,
        datasource_id: int,
    ) -> PermissionScopeSnapshot:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                return self._build_snapshot_once(
                    tenant_id=int(tenant_id),
                    user_id=int(user_id),
                    datasource_id=int(datasource_id),
                )
            except (PermissionScopeReadError, SQLAlchemyError) as exc:
                last_error = exc
        raise PermissionScopeUnavailableError(
            "无法读取一致的权限状态，请稍后重试。"
        ) from last_error

    def _build_snapshot_once(
        self,
        *,
        tenant_id: int,
        user_id: int,
        datasource_id: int,
    ) -> PermissionScopeSnapshot:
        dialect_name = str(self.engine.dialect.name).lower()
        if dialect_name not in {"postgresql", "sqlite"}:
            raise PermissionScopeReadError("unsupported authority database dialect")

        with self.engine.connect() as raw_connection:
            connection = raw_connection
            if dialect_name == "postgresql":
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
            transaction = connection.begin()
            try:
                if dialect_name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                return self._read_snapshot(
                    connection,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    datasource_id=datasource_id,
                )
            finally:
                transaction.rollback()

    def _read_snapshot(
        self,
        connection,
        *,
        tenant_id: int,
        user_id: int,
        datasource_id: int,
    ) -> PermissionScopeSnapshot:
        with Session(bind=connection) as session:
            state = self._read_authority_state(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                datasource_id=datasource_id,
            )
            version = _authority_version(state)
            header = PermissionScopeSnapshot(
                tenant_id=tenant_id,
                user_id=user_id,
                datasource_id=datasource_id,
                permission_version=version,
                schema_hash=state.schema_hash,
                allowed_object_keys=frozenset(),
                denied_object_keys=frozenset(),
                row_constraints_hash="",
            )
            cache_key = permission_cache_key(header)
            cached = self._read_cache(cache_key, header)
            if cached is not None:
                return cached

            current_user = self._authority_user(state)
            datasource = session.get(CoreDatasource, datasource_id)
            if datasource is None:
                raise PermissionScopeReadError("datasource authority disappeared")
            try:
                allowed = build_allowed_object_keys(
                    session,
                    tenant_id=tenant_id,
                    datasource=datasource,
                )
                denied = MetadataPermissionService.resolve_denied_objects(
                    session=session,
                    current_user=current_user,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                )
                constraints = get_applicable_row_permission_constraints(
                    session=session,
                    current_user=current_user,
                    ds=datasource,
                )
            except PermissionObjectProjectionError as exc:
                raise PermissionScopeReadError("invalid permission object projection") from exc
            except (MetadataPermissionValidationError, ValueError) as exc:
                raise PermissionScopeReadError("invalid permission authority") from exc

            snapshot = PermissionScopeSnapshot(
                tenant_id=tenant_id,
                user_id=user_id,
                datasource_id=datasource_id,
                permission_version=version,
                schema_hash=state.schema_hash,
                allowed_object_keys=frozenset(allowed - set(denied)),
                denied_object_keys=denied,
                row_constraints_hash=row_constraints_hash(constraints),
            )
            self._write_cache(cache_key, snapshot)
            return snapshot

    @staticmethod
    def _authority_user(state: PermissionAuthorityState) -> SimpleNamespace:
        platform_admin = state.system_role in SYSTEM_ADMIN_ROLES
        return SimpleNamespace(
            id=state.user_id,
            tenant_id=state.tenant_id,
            tenant_role=state.membership_role,
            workspace_role=state.membership_role,
            system_role=state.system_role,
            status=state.user_status,
            isAdmin=platform_admin,
            global_role="platform_admin" if platform_admin else "normal_user",
            has_workspace=True,
            workspace_status=(
                "platform_workspace_delegate" if platform_admin else "active"
            ),
        )

    def _read_authority_state(
        self,
        session: Session,
        *,
        tenant_id: int,
        user_id: int,
        datasource_id: int,
    ) -> PermissionAuthorityState:
        user = session.execute(
            select(UserModel.system_role, UserModel.status).where(UserModel.id == user_id)
        ).one_or_none()
        if user is None or int(user.status or 0) != 1:
            raise PermissionScopeReadError("user is missing or disabled")

        membership = session.execute(
            select(TenantUserModel.role, TenantUserModel.status).where(
                TenantUserModel.tenant_id == tenant_id,
                TenantUserModel.user_id == user_id,
            )
        ).one_or_none()
        if membership is None or int(membership.status or 0) != 1:
            raise PermissionScopeReadError("workspace membership is missing or disabled")

        bound_datasource_id = get_bound_datasource_id_for_tenant(session, tenant_id)
        if bound_datasource_id != datasource_id:
            raise PermissionScopeReadError("datasource is not bound to workspace")

        datasource = session.execute(
            select(
                CoreDatasource.catalog_complete,
                CoreDatasource.physical_schema_hash,
            ).where(CoreDatasource.id == datasource_id)
        ).one_or_none()
        if (
            datasource is None
            or not bool(datasource.catalog_complete)
            or not str(datasource.physical_schema_hash or "").strip()
        ):
            raise PermissionScopeReadError("datasource catalog is incomplete")

        datasource_access = session.execute(
            select(CoreDatasourceUser.role).where(
                CoreDatasourceUser.ds_id == datasource_id,
                CoreDatasourceUser.user_id == user_id,
            )
        ).one_or_none()
        coordinates = self._epoch_coordinates(
            tenant_id=tenant_id,
            user_id=user_id,
            datasource_id=datasource_id,
        )
        epoch_values = load_semantic_scope_epochs(session, coordinates=coordinates)
        epochs = tuple(
            (
                coordinate.scope_type.value,
                coordinate.tenant_id,
                coordinate.datasource_id,
                coordinate.subject_id,
                epoch_values[coordinate],
            )
            for coordinate in coordinates
        )
        return PermissionAuthorityState(
            tenant_id=tenant_id,
            user_id=user_id,
            datasource_id=datasource_id,
            system_role=normalize_system_role(user.system_role),
            user_status=int(user.status),
            membership_role=str(membership.role or "member").strip().lower(),
            membership_status=int(membership.status),
            datasource_access_recorded=datasource_access is not None,
            datasource_role=(
                str(datasource_access.role or "viewer").strip().lower()
                if datasource_access is not None
                else None
            ),
            bound_datasource_id=int(bound_datasource_id),
            schema_hash=str(datasource.physical_schema_hash),
            epochs=epochs,
        )

    @staticmethod
    def _epoch_coordinates(
        *,
        tenant_id: int,
        user_id: int,
        datasource_id: int,
    ) -> tuple[SemanticScopeCoordinate, ...]:
        return tuple(
            dict.fromkeys(
                (
                    SemanticScopeCoordinate(
                        SemanticScopeType.PERMISSION,
                        DEFAULT_TENANT_ID,
                        datasource_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.PERMISSION,
                        tenant_id,
                        datasource_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.SYSTEM_ROLE,
                        DEFAULT_TENANT_ID,
                        subject_id=user_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.MEMBERSHIP,
                        tenant_id,
                        subject_id=user_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.DATASOURCE_ACCESS,
                        tenant_id,
                        datasource_id,
                        user_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.DATASOURCE_ROLE,
                        tenant_id,
                        datasource_id,
                        user_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.TRACKING,
                        tenant_id,
                        datasource_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.DATASOURCE_BINDING,
                        tenant_id,
                    ),
                    SemanticScopeCoordinate(
                        SemanticScopeType.SCHEMA,
                        tenant_id,
                        datasource_id,
                    ),
                )
            )
        )

    def _read_cache(
        self,
        key: str,
        expected: PermissionScopeSnapshot,
    ) -> PermissionScopeSnapshot | None:
        if self.cache is None:
            return None
        try:
            cached = self.cache.get(key)
        except Exception:
            return None
        if not isinstance(cached, PermissionScopeSnapshot):
            return None
        if (
            cached.tenant_id,
            cached.user_id,
            cached.datasource_id,
            cached.permission_version,
            cached.schema_hash,
        ) != (
            expected.tenant_id,
            expected.user_id,
            expected.datasource_id,
            expected.permission_version,
            expected.schema_hash,
        ):
            return None
        return cached

    def _write_cache(self, key: str, snapshot: PermissionScopeSnapshot) -> None:
        if self.cache is None:
            return
        try:
            self.cache.set(key, snapshot)
        except Exception:
            return
