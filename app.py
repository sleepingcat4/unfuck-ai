import os
import json
import re
import hmac
from pathlib import Path
from datetime import datetime, timedelta

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    session,
)
from dotenv import load_dotenv


# ============================================================
# ENV
# ============================================================

load_dotenv()


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    os.urandom(32).hex()
)


app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=False,  # set True when behind HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=1024 * 1024,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

POSTS_DIR = BASE_DIR / "posts"

INDEX_FILE = POSTS_DIR / "index.jsonl"


POSTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)


if not INDEX_FILE.exists():
    INDEX_FILE.touch()


# ============================================================
# CONFIG
# ============================================================

PUBLISH_PHRASE = os.environ.get(
    "PUBLISH_PHRASE",
    ""
)


SAFE_FILENAME = re.compile(
    r"^[A-Za-z0-9_-]+\.md$"
)


MAX_TITLE_LENGTH = 200

MAX_AUTHOR_LENGTH = 100

MAX_MARKDOWN_LENGTH = 300_000


# ============================================================
# HELPERS
# ============================================================

def is_authenticated():
    return session.get(
        "writer_authenticated"
    ) is True


def is_mac_request():
    data = request.get_json(
        silent=True
    ) or {}

    device = data.get(
        "device",
        {}
    )

    if not isinstance(
        device,
        dict
    ):
        device = {}

    platform = str(
        device.get(
            "platform",
            ""
        )
    ).lower()

    user_agent = str(
        device.get(
            "userAgent",
            ""
        )
    ).lower()

    return (
        "mac" in platform
        or
        "macintosh" in user_agent
    )


def read_posts():
    posts = []


    if not INDEX_FILE.exists():
        return posts


    with INDEX_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()


            if not line:
                continue


            try:
                post = json.loads(
                    line
                )

                posts.append(
                    post
                )

            except json.JSONDecodeError as error:
                print(
                    "Skipping invalid JSONL line:",
                    error
                )


    posts.sort(
        key=lambda post: str(
            post.get(
                "date",
                ""
            )
        ),
        reverse=True
    )


    return posts


def write_posts(posts):
    with INDEX_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        for post in posts:

            file.write(
                json.dumps(
                    post,
                    ensure_ascii=False
                )
                + "\n"
            )


# ============================================================
# MAIN PAGE
# ============================================================

@app.route("/")
def index():
    return render_template(
        "index.html"
    )


# ============================================================
# POSTS INDEX
# ============================================================

@app.route(
    "/posts/index.jsonl"
)
def posts_index():

    if not INDEX_FILE.exists():
        return "", 200, {
            "Content-Type":
                "application/x-ndjson; charset=utf-8"
        }


    return send_from_directory(
        POSTS_DIR,
        "index.jsonl",
        mimetype="application/x-ndjson"
    )


# ============================================================
# INDIVIDUAL POST
# ============================================================

@app.route(
    "/posts/<filename>"
)
def get_post(filename):

    if not SAFE_FILENAME.fullmatch(
        filename
    ):
        return jsonify({
            "ok": False,
            "error": "Invalid filename."
        }), 400


    target = POSTS_DIR / filename


    if not target.exists():
        return jsonify({
            "ok": False,
            "error": "Post not found."
        }), 404


    return send_from_directory(
        POSTS_DIR,
        filename,
        mimetype="text/markdown"
    )


# ============================================================
# AUTH STATUS
# ============================================================

@app.get(
    "/api/auth/status"
)
def auth_status():

    return jsonify({
        "ok": True,
        "authenticated":
            is_authenticated()
    })


# ============================================================
# AUTH
# ============================================================

@app.post(
    "/api/auth"
)
def authenticate():

    data = request.get_json(
        silent=True
    ) or {}


    phrase = str(
        data.get(
            "phrase",
            ""
        )
    )


    if not PUBLISH_PHRASE:

        print(
            "WARNING: PUBLISH_PHRASE is not configured."
        )

        return jsonify({
            "ok": False,
            "error":
                "Server authentication is not configured."
        }), 500


    # --------------------------------------------------------
    # MAC CHECK
    # --------------------------------------------------------

    if not is_mac_request():

        return jsonify({
            "ok": False,
            "error":
                "Writing access is limited to macOS."
        }), 403


    # --------------------------------------------------------
    # PHRASE CHECK
    # --------------------------------------------------------

    valid_phrase = hmac.compare_digest(
        phrase,
        PUBLISH_PHRASE
    )


    if not valid_phrase:

        return jsonify({
            "ok": False,
            "error":
                "Incorrect publishing phrase."
        }), 403


    # --------------------------------------------------------
    # SESSION
    # --------------------------------------------------------

    session.clear()

    session.permanent = True

    session[
        "writer_authenticated"
    ] = True


    return jsonify({
        "ok": True,
        "authenticated": True
    })


# ============================================================
# LOGOUT
# ============================================================

@app.post(
    "/api/logout"
)
def logout():

    session.clear()


    return jsonify({
        "ok": True
    })


# ============================================================
# PUBLISH
# ============================================================

@app.post(
    "/api/publish"
)
def publish():

    # --------------------------------------------------------
    # AUTH
    # --------------------------------------------------------

    if not is_authenticated():

        return jsonify({
            "ok": False,
            "error":
                "Authentication required."
        }), 401


    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    ) or {}


    title = str(
        data.get(
            "title",
            ""
        )
    ).strip()


    author = str(
        data.get(
            "author",
            ""
        )
    ).strip()


    date = str(
        data.get(
            "date",
            ""
        )
    ).strip()


    filename = str(
        data.get(
            "file",
            ""
        )
    ).strip()


    markdown = str(
        data.get(
            "markdown",
            ""
        )
    )


    # --------------------------------------------------------
    # REQUIRED FIELDS
    # --------------------------------------------------------

    if not title:

        return jsonify({
            "ok": False,
            "error":
                "Title required."
        }), 400


    if not author:

        return jsonify({
            "ok": False,
            "error":
                "Author required."
        }), 400


    if not date:

        return jsonify({
            "ok": False,
            "error":
                "Date required."
        }), 400


    if not filename:

        return jsonify({
            "ok": False,
            "error":
                "Filename required."
        }), 400


    if not markdown.strip():

        return jsonify({
            "ok": False,
            "error":
                "Article cannot be empty."
        }), 400


    # --------------------------------------------------------
    # LENGTH CHECKS
    # --------------------------------------------------------

    if len(title) > MAX_TITLE_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Title is too long."
        }), 400


    if len(author) > MAX_AUTHOR_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Author is too long."
        }), 400


    if len(markdown) > MAX_MARKDOWN_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Article is too large."
        }), 413


    # --------------------------------------------------------
    # FILENAME CHECK
    # --------------------------------------------------------

    if not SAFE_FILENAME.fullmatch(
        filename
    ):

        return jsonify({
            "ok": False,
            "error":
                "Invalid filename."
        }), 400


    # --------------------------------------------------------
    # DATE CHECK
    # --------------------------------------------------------

    try:

        datetime.strptime(
            date,
            "%Y-%m-%d"
        )

    except ValueError:

        return jsonify({
            "ok": False,
            "error":
                "Date must use YYYY-MM-DD."
        }), 400


    # --------------------------------------------------------
    # SAFE PATH CHECK
    # --------------------------------------------------------

    target = (
        POSTS_DIR / filename
    ).resolve()


    posts_root = (
        POSTS_DIR.resolve()
    )


    if target.parent != posts_root:

        return jsonify({
            "ok": False,
            "error":
                "Invalid post path."
        }), 400


    # --------------------------------------------------------
    # WRITE MARKDOWN FILE
    # --------------------------------------------------------

    try:

        target.write_text(
            markdown,
            encoding="utf-8"
        )

    except OSError as error:

        print(
            "Failed writing post:",
            error
        )

        return jsonify({
            "ok": False,
            "error":
                "Could not write post."
        }), 500


    # --------------------------------------------------------
    # UPDATE JSONL
    # --------------------------------------------------------

    posts = read_posts()


    entry = {
        "title": title,
        "author": author,
        "date": date,
        "file": filename,
    }


    replaced = False


    for index, post in enumerate(
        posts
    ):

        if post.get(
            "file"
        ) == filename:

            posts[index] = entry

            replaced = True

            break


    if not replaced:

        posts.append(
            entry
        )


    posts.sort(
        key=lambda post: str(
            post.get(
                "date",
                ""
            )
        ),
        reverse=True
    )


    try:

        write_posts(
            posts
        )

    except OSError as error:

        print(
            "Failed writing JSONL:",
            error
        )

        return jsonify({
            "ok": False,
            "error":
                "Post was written but index update failed."
        }), 500


    return jsonify({
        "ok": True,
        "post": entry
    })


# ============================================================
# DEBUG ROUTE
# ============================================================

@app.get(
    "/api/debug/posts"
)
def debug_posts():

    return jsonify({
        "posts_dir":
            str(POSTS_DIR),

        "index_file":
            str(INDEX_FILE),

        "index_exists":
            INDEX_FILE.exists(),

        "posts":
            read_posts(),
    })


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def security_headers(response):

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"


    response.headers[
        "X-Frame-Options"
    ] = "DENY"


    response.headers[
        "Referrer-Policy"
    ] = (
        "strict-origin-when-cross-origin"
    )


    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), "
        "microphone=(), "
        "geolocation=()"
    )


    response.headers[
        "Content-Security-Policy"
    ] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )


    return response


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "error":
                "Endpoint not found."
        }), 404


    return (
        "Not found",
        404
    )


@app.errorhandler(413)
def too_large(error):

    return jsonify({
        "ok": False,
        "error":
            "Request is too large."
    }), 413


@app.errorhandler(500)
def server_error(error):

    print(
        "Internal server error:",
        error
    )


    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "error":
                "Internal server error."
        }), 500


    return (
        "Internal server error",
        500
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print(
        f"Posts directory: {POSTS_DIR}"
    )

    print(
        f"Posts index: {INDEX_FILE}"
    )

    print(
        f"Publish phrase configured: {bool(PUBLISH_PHRASE)}"
    )


    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )