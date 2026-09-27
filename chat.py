import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image
from werkzeug.utils import secure_filename
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


chat_bp = Blueprint(
    "chat",
    __name__,
    url_prefix="/chat",
)


ADJECTIVES = (
    "acid",
    "feral",
    "lucid",
    "noisy",
    "radical",
    "restless",
    "scarlet",
    "strange",
    "velvet",
    "wired",
)


NOUNS = (
    "badger",
    "comet",
    "gecko",
    "moth",
    "otter",
    "raven",
    "signal",
    "tiger",
    "viper",
    "walrus",
)


IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


USERNAME_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_-]{2,23}$"
)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    user_handle TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_passkeys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    credential_id TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    device_type TEXT,
    backed_up INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    body TEXT,
    image_name TEXT,
    image_type TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (body IS NOT NULL OR image_name IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_pair_time
ON chat_messages(sender_id, recipient_id, created_at);

CREATE TABLE IF NOT EXISTS chat_typing (
    user_id INTEGER NOT NULL,
    peer_id INTEGER NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY(user_id, peer_id)
);

CREATE TABLE IF NOT EXISTS chat_reports (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    reporter_id INTEGER NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    reported_user_id INTEGER NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    body_snapshot TEXT,
    image_name_snapshot TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(reporter_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_reports_created
ON chat_reports(created_at);
"""


def init_chat(app, base_dir):

    data_dir = Path(
        os.environ.get(
            "CHAT_DATA_DIR",
            Path(base_dir) / "data",
        )
    )


    upload_dir = Path(
        os.environ.get(
            "CHAT_UPLOAD_DIR",
            data_dir / "chat_uploads",
        )
    )


    data_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    app.config.update(
        CHAT_DATABASE=str(
            data_dir / "chat.db"
        ),
        CHAT_UPLOAD_DIR=str(
            upload_dir
        ),
        CHAT_RP_ID=os.environ.get(
            "CHAT_RP_ID",
            "",
        ).strip(),
        CHAT_ORIGIN=os.environ.get(
            "CHAT_ORIGIN",
            "",
        ).strip(),
    )


    with sqlite3.connect(
        app.config["CHAT_DATABASE"]
    ) as database:

        database.executescript(
            SCHEMA
        )


        columns = {
            row[1]
            for row in database.execute(
                "PRAGMA table_info(chat_users)"
            ).fetchall()
        }


        if "user_handle" not in columns:

            database.execute(
                "ALTER TABLE chat_users ADD COLUMN user_handle TEXT"
            )


        missing_handles = database.execute(
            "SELECT id FROM chat_users WHERE user_handle IS NULL OR user_handle = ''"
        ).fetchall()


        for row in missing_handles:

            database.execute(
                "UPDATE chat_users SET user_handle = ? WHERE id = ?",
                (
                    bytes_to_base64url(
                        secrets.token_bytes(32)
                    ),
                    row[0],
                ),
            )


        database.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_users_handle ON chat_users(user_handle)"
        )


        database.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_users_username_nocase "
            "ON chat_users(username COLLATE NOCASE)"
        )


        database.commit()


    app.teardown_appcontext(
        close_database
    )


def database():

    if "chat_database" not in g:

        connection = sqlite3.connect(
            current_app.config[
                "CHAT_DATABASE"
            ],
            timeout=10,
        )


        connection.row_factory = (
            sqlite3.Row
        )


        connection.execute(
            "PRAGMA foreign_keys = ON"
        )


        connection.execute(
            "PRAGMA journal_mode = WAL"
        )


        g.chat_database = (
            connection
        )


    return g.chat_database


def close_database(error=None):

    connection = g.pop(
        "chat_database",
        None,
    )


    if connection is not None:

        connection.close()


def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def chat_user():

    user_id = session.get(
        "chat_user_id"
    )


    if not user_id:
        return None


    return database().execute(
        """
        SELECT id, username, user_handle, created_at
        FROM chat_users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def chat_login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if chat_user() is None:

            return jsonify({
                "ok": False,
                "error": "Sign in to use chat.",
            }), 401


        return view(
            *args,
            **kwargs,
        )


    return wrapped


def csrf_token():

    token = session.get(
        "chat_csrf_token"
    )


    if not token:

        token = secrets.token_urlsafe(
            32
        )


        session[
            "chat_csrf_token"
        ] = token


    return token


@chat_bp.before_request
def verify_csrf():

    if request.method not in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        return None


    submitted = (
        request.headers.get(
            "X-CSRF-Token"
        )
        or request.form.get(
            "csrf_token"
        )
    )


    if (
        not submitted
        or not secrets.compare_digest(
            submitted,
            csrf_token(),
        )
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid security token. Refresh the page.",
        }), 400


    return None


def random_username():

    connection = database()


    for _ in range(100):

        username = (
            f"{secrets.choice(ADJECTIVES)}-"
            f"{secrets.choice(NOUNS)}-"
            f"{secrets.randbelow(10000):04d}"
        )


        existing = connection.execute(
            """
            SELECT 1
            FROM chat_users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()


        if existing is None:
            return username


    raise RuntimeError(
        "Could not generate a username."
    )


def row_user(row):

    return {
        "id": row["id"],
        "username": row["username"],
        "createdAt": row["created_at"],
    }


def row_message(row, user_id):

    deleted = bool(
        row["deleted_at"]
    )


    image_url = None


    if (
        row["image_name"]
        and not deleted
    ):

        image_url = url_for(
            "chat.chat_media",
            filename=row[
                "image_name"
            ],
        )


    return {
        "id": row["id"],
        "senderId": row["sender_id"],
        "recipientId": row[
            "recipient_id"
        ],
        "mine": (
            row["sender_id"]
            == user_id
        ),
        "body": (
            None
            if deleted
            else row["body"]
        ),
        "imageUrl": image_url,
        "createdAt": row[
            "created_at"
        ],
        "deleted": deleted,
        "reported": (
            bool(row["reported"])
            if "reported" in row.keys()
            else False
        ),
    }


def relying_party_id():

    return (
        current_app.config[
            "CHAT_RP_ID"
        ]
        or request.host.split(
            ":",
            1,
        )[0]
    )


def expected_origin():

    return (
        current_app.config[
            "CHAT_ORIGIN"
        ]
        or request.host_url.rstrip(
            "/"
        )
    )


def public_key_rows(user_id):

    return database().execute(
        """
        SELECT *
        FROM chat_passkeys
        WHERE user_id = ?
        ORDER BY id
        """,
        (user_id,),
    ).fetchall()


def login_is_rate_limited():

    now = time.time()


    attempts = [
        value
        for value in session.get(
            "chat_login_attempts",
            [],
        )
        if now - float(value) < 300
    ]


    if len(attempts) >= 8:

        session[
            "chat_login_attempts"
        ] = attempts


        return True


    attempts.append(
        now
    )


    session[
        "chat_login_attempts"
    ] = attempts


    return False


@chat_bp.get("")
@chat_bp.get("/")
def chat_page():

    if request.host.split(":", 1)[0] in {
        "127.0.0.1",
        "0.0.0.0",
    }:

        return redirect(
            request.url.replace(
                f"://{request.host.split(':', 1)[0]}",
                "://localhost",
                1,
            ),
            code=302,
        )

    user = chat_user()


    return render_template(
        "chat.html",
        chat_user=(
            row_user(user)
            if user
            else None
        ),
        chat_csrf=csrf_token(),
    )


@chat_bp.post("/api/auth/logout")
def chat_logout():

    for key in list(
        session.keys()
    ):

        if key.startswith(
            "chat_"
        ):

            session.pop(
                key,
                None,
            )


    return jsonify({
        "ok": True,
    })


@chat_bp.get("/api/bootstrap")
@chat_login_required
def bootstrap():

    user = chat_user()


    peers = database().execute(
        """
        SELECT
            u.id,
            u.username,
            u.created_at,
            MAX(m.created_at) AS last_at
        FROM chat_users AS u
        JOIN chat_messages AS m
          ON (
              m.sender_id = ?
              AND m.recipient_id = u.id
          )
          OR (
              m.recipient_id = ?
              AND m.sender_id = u.id
          )
        GROUP BY u.id, u.username, u.created_at
        ORDER BY last_at DESC
        LIMIT 40
        """,
        (
            user["id"],
            user["id"],
        ),
    ).fetchall()


    return jsonify({
        "ok": True,
        "me": row_user(user),
        "peers": [
            row_user(peer)
            for peer in peers
        ],
        "hasPasskey": bool(
            public_key_rows(
                user["id"]
            )
        ),
    })


@chat_bp.get("/api/users")
@chat_login_required
def search_users():

    query = request.args.get(
        "q",
        "",
    ).strip().lower()


    if len(query) < 2:

        return jsonify({
            "ok": True,
            "users": [],
        })


    escaped = (
        query
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


    user = chat_user()


    rows = database().execute(
        """
        SELECT id, username, created_at
        FROM chat_users
        WHERE id != ?
          AND lower(username) LIKE ? ESCAPE '\\'
        ORDER BY username
        LIMIT 20
        """,
        (
            user["id"],
            f"%{escaped}%",
        ),
    ).fetchall()


    return jsonify({
        "ok": True,
        "users": [
            row_user(row)
            for row in rows
        ],
    })


@chat_bp.patch("/api/profile/username")
@chat_login_required
def change_username():

    data = request.get_json(
        silent=True
    ) or {}


    username = str(
        data.get(
            "username",
            "",
        )
    ).strip().lower()


    if not USERNAME_PATTERN.fullmatch(
        username
    ):

        return jsonify({
            "ok": False,
            "error": (
                "Use 3–24 lowercase letters, numbers, "
                "hyphens, or underscores."
            ),
        }), 400


    user = chat_user()


    if username == user["username"].lower():

        return jsonify({
            "ok": True,
            "username": user["username"],
        })


    connection = database()


    try:

        connection.execute(
            """
            UPDATE chat_users
            SET username = ?
            WHERE id = ?
            """,
            (
                username,
                user["id"],
            ),
        )


        connection.commit()


    except sqlite3.IntegrityError:

        connection.rollback()


        return jsonify({
            "ok": False,
            "error": "That username is already taken.",
        }), 409


    return jsonify({
        "ok": True,
        "username": username,
    })


def peer_or_404(peer_id):

    user = chat_user()


    try:

        peer_id = int(
            peer_id
        )

    except (
        TypeError,
        ValueError,
    ):

        abort(400)


    if peer_id == user["id"]:
        abort(400)


    peer = database().execute(
        """
        SELECT id, username, created_at
        FROM chat_users
        WHERE id = ?
        """,
        (peer_id,),
    ).fetchone()


    if peer is None:
        abort(404)


    return peer


@chat_bp.get("/api/messages/<int:peer_id>")
@chat_login_required
def get_messages(peer_id):

    peer = peer_or_404(
        peer_id
    )


    user = chat_user()


    rows = database().execute(
        """
        SELECT
            m.*,
            EXISTS (
                SELECT 1
                FROM chat_reports AS r
                WHERE r.message_id = m.id
                  AND r.reporter_id = ?
            ) AS reported
        FROM chat_messages AS m
        WHERE (
            sender_id = ?
            AND recipient_id = ?
        )
        OR (
            sender_id = ?
            AND recipient_id = ?
        )
        ORDER BY created_at DESC
        LIMIT 120
        """,
        (
            user["id"],
            user["id"],
            peer["id"],
            peer["id"],
            user["id"],
        ),
    ).fetchall()


    typing = database().execute(
        """
        SELECT 1
        FROM chat_typing
        WHERE user_id = ?
          AND peer_id = ?
          AND expires_at > ?
        """,
        (
            peer["id"],
            user["id"],
            time.time(),
        ),
    ).fetchone()


    return jsonify({
        "ok": True,
        "messages": [
            row_message(
                row,
                user["id"],
            )
            for row in reversed(
                rows
            )
        ],
        "typing": bool(
            typing
        ),
    })


@chat_bp.post("/api/messages")
@chat_login_required
def send_message():

    data = request.get_json(
        silent=True
    ) or {}


    peer = peer_or_404(
        data.get(
            "recipientId"
        )
    )


    body = str(
        data.get(
            "body",
            "",
        )
    ).strip()


    if (
        not body
        or len(body) > 4000
    ):

        return jsonify({
            "ok": False,
            "error": "Messages must contain 1 to 4000 characters.",
        }), 400


    user = chat_user()


    message_id = str(
        uuid.uuid4()
    )


    created_at = now_iso()


    connection = database()


    connection.execute(
        """
        INSERT INTO chat_messages (
            id,
            sender_id,
            recipient_id,
            body,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            message_id,
            user["id"],
            peer["id"],
            body,
            created_at,
        ),
    )


    connection.execute(
        """
        DELETE FROM chat_typing
        WHERE user_id = ?
          AND peer_id = ?
        """,
        (
            user["id"],
            peer["id"],
        ),
    )


    connection.commit()


    row = connection.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE id = ?
        """,
        (message_id,),
    ).fetchone()


    return jsonify({
        "ok": True,
        "message": row_message(
            row,
            user["id"],
        ),
    }), 201


@chat_bp.post("/api/typing")
@chat_login_required
def set_typing():

    data = request.get_json(
        silent=True
    ) or {}


    peer = peer_or_404(
        data.get(
            "recipientId"
        )
    )


    user = chat_user()


    connection = database()


    if data.get(
        "typing"
    ):

        connection.execute(
            """
            INSERT INTO chat_typing (
                user_id,
                peer_id,
                expires_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, peer_id)
            DO UPDATE SET expires_at = excluded.expires_at
            """,
            (
                user["id"],
                peer["id"],
                time.time() + 4,
            ),
        )


    else:

        connection.execute(
            """
            DELETE FROM chat_typing
            WHERE user_id = ?
              AND peer_id = ?
            """,
            (
                user["id"],
                peer["id"],
            ),
        )


    connection.commit()


    return jsonify({
        "ok": True,
    })


@chat_bp.post("/api/messages/<message_id>/report")
@chat_login_required
def report_message(message_id):

    user = chat_user()


    message = database().execute(
        """
        SELECT *
        FROM chat_messages
        WHERE id = ?
          AND recipient_id = ?
        """,
        (
            message_id,
            user["id"],
        ),
    ).fetchone()


    if message is None:

        return jsonify({
            "ok": False,
            "error": "Only received messages can be reported.",
        }), 404


    data = request.get_json(
        silent=True
    ) or {}


    reason = str(
        data.get(
            "reason",
            "user_reported",
        )
    ).strip().lower()


    allowed_reasons = {
        "user_reported",
        "spam",
        "harassment",
        "dangerous",
        "other",
    }


    if reason not in allowed_reasons:
        reason = "other"


    connection = database()


    connection.execute(
        """
        INSERT INTO chat_reports (
            id,
            message_id,
            reporter_id,
            reported_user_id,
            reason,
            body_snapshot,
            image_name_snapshot,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reporter_id, message_id)
        DO NOTHING
        """,
        (
            str(uuid.uuid4()),
            message["id"],
            user["id"],
            message["sender_id"],
            reason,
            message["body"],
            message["image_name"],
            now_iso(),
        ),
    )


    connection.commit()


    return jsonify({
        "ok": True,
        "reported": True,
    })


@chat_bp.delete("/api/messages/<message_id>")
@chat_login_required
def unsend_message(message_id):

    user = chat_user()


    connection = database()


    message = connection.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE id = ?
          AND sender_id = ?
        """,
        (
            message_id,
            user["id"],
        ),
    ).fetchone()


    if message is None:

        return jsonify({
            "ok": False,
            "error": "Only your own messages can be unsent.",
        }), 404


    if message["deleted_at"]:

        return jsonify({
            "ok": True,
        })


    connection.execute(
        """
        UPDATE chat_messages
        SET body = '',
            image_name = NULL,
            image_type = NULL,
            deleted_at = ?
        WHERE id = ?
        """,
        (
            now_iso(),
            message_id,
        ),
    )


    connection.commit()


    if message["image_name"]:

        image_path = Path(
            current_app.config[
                "CHAT_UPLOAD_DIR"
            ]
        ) / message["image_name"]


        try:

            image_path.unlink(
                missing_ok=True
            )

        except OSError:
            pass


    return jsonify({
        "ok": True,
    })


@chat_bp.post("/api/images")
@chat_login_required
def upload_image():

    peer = peer_or_404(
        request.form.get(
            "recipientId"
        )
    )


    upload = request.files.get(
        "image"
    )


    if upload is None:

        return jsonify({
            "ok": False,
            "error": "Choose an image first.",
        }), 400


    raw = upload.read()


    if len(raw) > 8 * 1024 * 1024:

        return jsonify({
            "ok": False,
            "error": "Images must be smaller than 8 MB.",
        }), 413


    try:

        image = Image.open(
            io.BytesIO(raw)
        )


        image.verify()


        mime = Image.MIME.get(
            image.format
        )


    except Exception:

        return jsonify({
            "ok": False,
            "error": "That file is not a valid image.",
        }), 400


    if mime not in IMAGE_TYPES:

        return jsonify({
            "ok": False,
            "error": "Use a JPG, PNG, WebP, or GIF image.",
        }), 400


    image_name = (
        f"{uuid.uuid4().hex}"
        f"{IMAGE_TYPES[mime]}"
    )


    image_path = Path(
        current_app.config[
            "CHAT_UPLOAD_DIR"
        ]
    ) / image_name


    image_path.write_bytes(
        raw
    )


    caption = str(
        request.form.get(
            "caption",
            "",
        )
    ).strip()


    if len(caption) > 4000:

        image_path.unlink(
            missing_ok=True
        )


        return jsonify({
            "ok": False,
            "error": "Captions must be under 4000 characters.",
        }), 400


    user = chat_user()


    message_id = str(
        uuid.uuid4()
    )


    connection = database()


    connection.execute(
        """
        INSERT INTO chat_messages (
            id,
            sender_id,
            recipient_id,
            body,
            image_name,
            image_type,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            user["id"],
            peer["id"],
            caption or None,
            image_name,
            mime,
            now_iso(),
        ),
    )


    connection.commit()


    row = connection.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE id = ?
        """,
        (message_id,),
    ).fetchone()


    return jsonify({
        "ok": True,
        "message": row_message(
            row,
            user["id"],
        ),
    }), 201


@chat_bp.get("/media/<filename>")
@chat_login_required
def chat_media(filename):

    safe = secure_filename(
        filename
    )


    if safe != filename:
        abort(404)


    user = chat_user()


    allowed = database().execute(
        """
        SELECT image_type
        FROM chat_messages
        WHERE image_name = ?
          AND deleted_at IS NULL
          AND (
              sender_id = ?
              OR recipient_id = ?
          )
        LIMIT 1
        """,
        (
            filename,
            user["id"],
            user["id"],
        ),
    ).fetchone()


    if allowed is None:
        abort(404)


    return send_from_directory(
        current_app.config[
            "CHAT_UPLOAD_DIR"
        ],
        filename,
        mimetype=allowed[
            "image_type"
        ],
        max_age=3600,
    )


@chat_bp.post("/api/passkeys/register/options")
def passkey_registration_options():

    user = chat_user()


    if user:

        keys = public_key_rows(
            user["id"]
        )


        username = user[
            "username"
        ]


        user_handle = (
            base64url_to_bytes(
                user["user_handle"]
            )
        )


    else:

        keys = []


        username = random_username()


        user_handle = secrets.token_bytes(
            32
        )


        session[
            "chat_pending_username"
        ] = username


        session[
            "chat_pending_user_handle"
        ] = bytes_to_base64url(
            user_handle
        )


    options = generate_registration_options(
        rp_id=relying_party_id(),
        rp_name="Unfuck AI",
        user_id=user_handle,
        user_name=username,
        user_display_name=username,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(
                    key[
                        "credential_id"
                    ]
                )
            )
            for key in keys
        ],
        authenticator_selection=(
            AuthenticatorSelectionCriteria(
                resident_key=(
                    ResidentKeyRequirement.REQUIRED
                ),
                user_verification=(
                    UserVerificationRequirement.REQUIRED
                ),
            )
        ),
    )


    session[
        "chat_passkey_register_challenge"
    ] = bytes_to_base64url(
        options.challenge
    )


    return current_app.response_class(
        options_to_json(
            options
        ),
        mimetype="application/json",
    )


@chat_bp.post("/api/passkeys/register/verify")
def passkey_registration_verify():

    challenge = session.pop(
        "chat_passkey_register_challenge",
        None,
    )


    if not challenge:

        return jsonify({
            "ok": False,
            "error": "Passkey setup expired. Try again.",
        }), 400


    try:

        verified = verify_registration_response(
            credential=request.get_json(),
            expected_challenge=(
                base64url_to_bytes(
                    challenge
                )
            ),
            expected_rp_id=(
                relying_party_id()
            ),
            expected_origin=(
                expected_origin()
            ),
            require_user_verification=True,
        )


    except Exception as error:

        current_app.logger.warning(
            "Passkey registration failed: %s",
            error,
        )


        return jsonify({
            "ok": False,
            "error": "The passkey could not be verified.",
        }), 400


    user = chat_user()


    pending_username = session.get(
        "chat_pending_username"
    )


    pending_handle = session.get(
        "chat_pending_user_handle"
    )


    if (
        user is None
        and (
            not pending_username
            or not pending_handle
        )
    ):

        return jsonify({
            "ok": False,
            "error": "Passkey setup expired. Start again.",
        }), 400


    try:

        connection = database()


        if user is None:

            user_columns = {
                row["name"]: row
                for row in connection.execute(
                    "PRAGMA table_info(chat_users)"
                ).fetchall()
            }


            legacy_password = user_columns.get(
                "password_hash"
            )


            if (
                legacy_password
                and legacy_password["notnull"]
            ):

                cursor = connection.execute(
                    """
                    INSERT INTO chat_users (
                        username,
                        password_hash,
                        user_handle,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        pending_username,
                        "!passkey-only-" + secrets.token_hex(32),
                        pending_handle,
                        now_iso(),
                    ),
                )


            else:

                cursor = connection.execute(
                    """
                    INSERT INTO chat_users (
                        username,
                        user_handle,
                        created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        pending_username,
                        pending_handle,
                        now_iso(),
                    ),
                )


            user_id = cursor.lastrowid


        else:

            user_id = user["id"]


        connection.execute(
            """
            INSERT INTO chat_passkeys (
                user_id,
                credential_id,
                public_key,
                sign_count,
                device_type,
                backed_up,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                bytes_to_base64url(
                    verified.credential_id
                ),
                bytes_to_base64url(
                    verified.credential_public_key
                ),
                verified.sign_count,
                str(
                    verified.credential_device_type
                ),
                int(
                    verified.credential_backed_up
                ),
                now_iso(),
            ),
        )


        connection.commit()


        session[
            "chat_user_id"
        ] = user_id


        session.pop(
            "chat_pending_username",
            None,
        )


        session.pop(
            "chat_pending_user_handle",
            None,
        )


    except sqlite3.IntegrityError:

        connection.rollback()

        return jsonify({
            "ok": False,
            "error": "That passkey is already registered.",
        }), 409


    return jsonify({
        "ok": True,
        "username": (
            user["username"]
            if user
            else pending_username
        ),
    })


@chat_bp.post("/api/passkeys/login/options")
def passkey_login_options():

    if login_is_rate_limited():

        return jsonify({
            "ok": False,
            "error": "Too many attempts. Wait five minutes.",
        }), 429


    options = generate_authentication_options(
        rp_id=relying_party_id(),
        user_verification=(
            UserVerificationRequirement.REQUIRED
        ),
    )


    session[
        "chat_passkey_login_challenge"
    ] = bytes_to_base64url(
        options.challenge
    )


    return current_app.response_class(
        options_to_json(
            options
        ),
        mimetype="application/json",
    )


@chat_bp.post("/api/passkeys/login/verify")
def passkey_login_verify():

    challenge = session.pop(
        "chat_passkey_login_challenge",
        None,
    )


    credential = request.get_json(
        silent=True
    ) or {}


    key = database().execute(
        """
        SELECT *
        FROM chat_passkeys
        WHERE credential_id = ?
        """,
        (
            credential.get(
                "id"
            ),
        ),
    ).fetchone()


    if (
        not challenge
        or key is None
    ):

        return jsonify({
            "ok": False,
            "error": "Passkey sign-in expired. Try again.",
        }), 400


    try:

        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=(
                base64url_to_bytes(
                    challenge
                )
            ),
            expected_rp_id=(
                relying_party_id()
            ),
            expected_origin=(
                expected_origin()
            ),
            credential_public_key=(
                base64url_to_bytes(
                    key["public_key"]
                )
            ),
            credential_current_sign_count=(
                key["sign_count"]
            ),
            require_user_verification=True,
        )


    except Exception as error:

        current_app.logger.warning(
            "Passkey login failed: %s",
            error,
        )


        return jsonify({
            "ok": False,
            "error": "The passkey could not be verified.",
        }), 400


    connection = database()


    connection.execute(
        """
        UPDATE chat_passkeys
        SET sign_count = ?
        WHERE id = ?
        """,
        (
            verified.new_sign_count,
            key["id"],
        ),
    )


    connection.commit()


    session[
        "chat_user_id"
    ] = key["user_id"]


    session.pop(
        "chat_login_attempts",
        None,
    )


    return jsonify({
        "ok": True,
    })
