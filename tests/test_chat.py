import sqlite3
from types import SimpleNamespace

import pytest

import app as application
import chat
from chat import SCHEMA


@pytest.fixture()
def client(tmp_path):
    application.app.config.update(
        TESTING=True,
        CHAT_DATABASE=str(tmp_path / "chat.db"),
        CHAT_UPLOAD_DIR=str(tmp_path / "uploads"),
        CHAT_RP_ID="localhost",
        CHAT_ORIGIN="http://localhost",
    )
    (tmp_path / "uploads").mkdir()
    with sqlite3.connect(application.app.config["CHAT_DATABASE"]) as database:
        database.executescript(SCHEMA)
    with application.app.test_client() as test_client:
        yield test_client


def csrf(client):
    client.get("/chat")
    with client.session_transaction() as state:
        return state["chat_csrf_token"]


def register_passkey(client, monkeypatch, credential_id):
    token = csrf(client)
    options = client.post(
        "/chat/api/passkeys/register/options",
        json={},
        headers={"X-CSRF-Token": token},
    )
    assert options.status_code == 200

    monkeypatch.setattr(
        chat,
        "verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=credential_id,
            credential_public_key=b"public-key-" + credential_id,
            sign_count=0,
            credential_device_type="single_device",
            credential_backed_up=False,
        ),
    )
    response = client.post(
        "/chat/api/passkeys/register/verify",
        json={"id": "browser-credential"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return response.get_json()


def test_passkey_is_the_only_account_credential(client, monkeypatch):
    loopback = client.get(
        "/chat/",
        base_url="http://127.0.0.1:5001",
    )
    assert loopback.status_code == 302
    assert loopback.headers["Location"].startswith(
        "http://localhost:5001/chat/"
    )

    page = client.get("/chat/")
    assert b"No site password" not in page.data
    assert b"no hack" in page.data

    favicon = client.get("/unfuck.png")
    assert favicon.status_code == 200
    assert favicon.mimetype == "image/png"

    assert client.post("/chat/api/auth/register", json={}).status_code == 404
    assert client.post("/chat/api/auth/login", json={}).status_code == 404

    options = client.post(
        "/chat/api/passkeys/register/options",
        json={},
        headers={"X-CSRF-Token": csrf(client)},
    ).get_json()
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"

    with sqlite3.connect(application.app.config["CHAT_DATABASE"]) as database:
        assert database.execute("SELECT COUNT(*) FROM chat_users").fetchone()[0] == 0

    result = register_passkey(client, monkeypatch, b"credential-one")
    assert result["username"].count("-") == 2
    assert client.get("/chat/api/bootstrap").status_code == 200

    with sqlite3.connect(application.app.config["CHAT_DATABASE"]) as database:
        columns = {
            row[1]
            for row in database.execute("PRAGMA table_info(chat_users)")
        }
        assert "password_hash" not in columns
        user = database.execute(
            "SELECT username, user_handle FROM chat_users"
        ).fetchone()
        assert user[0] == result["username"]
        assert user[1]


def test_offline_message_and_unsend(client, monkeypatch):
    first = client
    register_passkey(first, monkeypatch, b"credential-first")
    first_data = first.get("/chat/api/bootstrap").get_json()["me"]
    first_token = csrf(first)

    second = application.app.test_client()
    register_passkey(second, monkeypatch, b"credential-second")
    second_data = second.get("/chat/api/bootstrap").get_json()["me"]

    renamed = first.patch(
        "/chat/api/profile/username",
        json={"username": "shared-name"},
        headers={"X-CSRF-Token": first_token},
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["username"] == "shared-name"

    duplicate = second.patch(
        "/chat/api/profile/username",
        json={"username": "SHARED-NAME"},
        headers={"X-CSRF-Token": csrf(second)},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"] == "That username is already taken."

    sent = first.post(
        "/chat/api/messages",
        json={"recipientId": second_data["id"], "body": "stored while you are gone"},
        headers={"X-CSRF-Token": first_token},
    )
    assert sent.status_code == 201
    message_id = sent.get_json()["message"]["id"]

    recipient_peers = second.get(
        "/chat/api/bootstrap"
    ).get_json()["peers"]
    assert recipient_peers[0]["id"] == first_data["id"]

    received = second.get(f"/chat/api/messages/{first_data['id']}")
    assert received.get_json()["messages"][0]["body"] == "stored while you are gone"

    report = second.post(
        f"/chat/api/messages/{message_id}/report",
        json={"reason": "harassment"},
        headers={"X-CSRF-Token": csrf(second)},
    )
    assert report.status_code == 200
    reported_messages = second.get(
        f"/chat/api/messages/{first_data['id']}"
    ).get_json()["messages"]
    assert reported_messages[0]["reported"] is True

    with sqlite3.connect(application.app.config["CHAT_DATABASE"]) as database:
        stored_report = database.execute(
            "SELECT reporter_id, reported_user_id, reason, body_snapshot FROM chat_reports"
        ).fetchone()
        assert stored_report == (
            second_data["id"],
            first_data["id"],
            "harassment",
            "stored while you are gone",
        )

    unsent = first.delete(
        f"/chat/api/messages/{message_id}",
        headers={"X-CSRF-Token": first_token},
    )
    assert unsent.status_code == 200
    after = second.get(f"/chat/api/messages/{first_data['id']}").get_json()
    assert after["messages"][0]["deleted"] is True
