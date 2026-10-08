from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, text

from apps.system.api.user_theme import router
from common.core.deps import get_current_user, get_session


@pytest.fixture
def account_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sys_user (id BIGINT PRIMARY KEY, color_theme VARCHAR(5) NOT NULL DEFAULT 'light')"))
        connection.execute(text('INSERT INTO sys_user (id) VALUES (1), (2)'))
    identity = {'id': 1, 'tenant_id': 11}
    app = FastAPI()
    app.include_router(router, prefix='/user')
    def session():
        with Session(engine) as value:
            yield value
    def current_user():
        if not identity['id']:
            raise HTTPException(401, 'Login required')
        return SimpleNamespace(**identity)
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_user] = current_user
    with TestClient(app) as client:
        client.headers['X-SHUZHI-ACCOUNT-ID'] = '1'
        yield client, identity
    engine.dispose()


def test_theme_survives_new_requests_and_workspace_changes_but_is_account_private(account_api):
    client, identity = account_api
    assert client.get('/user/color-theme').json() == {'theme': 'light'}
    assert client.put('/user/color-theme', json={'theme': 'dark'}).json() == {'theme': 'dark'}
    identity['tenant_id'] = 22
    assert client.get('/user/color-theme').json() == {'theme': 'dark'}
    identity['id'] = 2
    client.headers['X-SHUZHI-ACCOUNT-ID'] = '2'
    assert client.get('/user/color-theme').json() == {'theme': 'light'}
    identity['id'] = 1
    client.headers['X-SHUZHI-ACCOUNT-ID'] = '1'
    assert client.get('/user/color-theme').json() == {'theme': 'dark'}


@pytest.mark.parametrize('payload', [{'theme': 'auto'}, {'theme': None}, {}, {'theme': 'dark', 'user_id': 2}])
def test_invalid_or_cross_account_payload_cannot_change_preferences(account_api, payload):
    client, _ = account_api
    assert client.put('/user/color-theme', json=payload).status_code == 422
    assert client.get('/user/color-theme').json() == {'theme': 'light'}


def test_login_required_and_missing_account_is_not_silently_created(account_api):
    client, identity = account_api
    identity['id'] = None
    assert client.get('/user/color-theme').status_code == 401
    identity['id'] = 999
    client.headers['X-SHUZHI-ACCOUNT-ID'] = '999'
    assert client.get('/user/color-theme').status_code == 404
    assert client.put('/user/color-theme', json={'theme': 'dark'}).status_code == 404


@pytest.mark.parametrize('header', ['X-SHUZHI-ASSISTANT-TOKEN', 'X-SHUZHI-ASK-TOKEN'])
def test_embedded_identity_cannot_change_owners_account_preference(account_api, header):
    client, _ = account_api
    assert client.put('/user/color-theme', json={'theme': 'dark'}, headers={header: 'fixture'}).status_code == 403


def test_request_started_by_previous_account_cannot_modify_new_session(account_api):
    client, identity = account_api
    identity['id'] = 2
    assert client.get('/user/color-theme').status_code == 409
    assert client.put('/user/color-theme', json={'theme': 'dark'}).status_code == 409
    client.headers['X-SHUZHI-ACCOUNT-ID'] = '2'
    assert client.get('/user/color-theme').json() == {'theme': 'light'}
