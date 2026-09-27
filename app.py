import os
import json
import re
import hmac
import tempfile

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
from chat import chat_bp, init_chat


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"
INDEX_FILE = POSTS_DIR / "index.jsonl"


POSTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


if not INDEX_FILE.exists():
    INDEX_FILE.touch()


app = Flask(__name__)


FLASK_SECRET_KEY = os.environ.get(
    "FLASK_SECRET_KEY",
    "",
).strip()


if not FLASK_SECRET_KEY:

    FLASK_SECRET_KEY = os.urandom(
        32
    ).hex()

    print(
        "WARNING: FLASK_SECRET_KEY is not configured."
    )


app.secret_key = FLASK_SECRET_KEY


PUBLISH_PHRASE = os.environ.get(
    "PUBLISH_PHRASE",
    "",
)


MACOS_ONLY = os.environ.get(
    "MACOS_ONLY",
    "true",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


IS_PRODUCTION = os.environ.get(
    "FLASK_ENV",
    "",
).strip().lower() == "production"


SESSION_COOKIE_SECURE = os.environ.get(
    "SESSION_COOKIE_SECURE",
    "true" if IS_PRODUCTION else "false",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=2
    ),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)


init_chat(
    app,
    BASE_DIR,
)


app.register_blueprint(
    chat_bp
)


@app.get("/unfuck.png")
def favicon():

    return send_from_directory(
        BASE_DIR,
        "unfuck.png",
        mimetype="image/png",
        max_age=86400,
    )


@app.get("/favicon.ico")
def favicon_ico():

    return favicon()


SAFE_FILENAME = re.compile(
    r"^[A-Za-z0-9_-]+\.md$"
)


MAX_TITLE_LENGTH = 200
MAX_AUTHOR_LENGTH = 100
MAX_MARKDOWN_LENGTH = 300_000


def is_authenticated():

    return (
        session.get(
            "writer_authenticated"
        )
        is True
    )


def is_mac_request():

    data = request.get_json(
        silent=True
    ) or {}


    device = data.get(
        "device",
        {},
    )


    if not isinstance(
        device,
        dict,
    ):
        device = {}


    platform = str(
        device.get(
            "platform",
            "",
        )
    ).lower()


    user_agent = str(
        device.get(
            "userAgent",
            "",
        )
    ).lower()


    return (
        "mac" in platform
        or
        "macintosh" in user_agent
    )


def normalize_post(post):

    if not isinstance(
        post,
        dict,
    ):
        return None


    title = str(
        post.get(
            "title",
            "",
        )
    ).strip()


    author = str(
        post.get(
            "author",
            "",
        )
    ).strip()


    date = str(
        post.get(
            "date",
            "",
        )
    ).strip()


    filename = str(
        post.get(
            "file",
            "",
        )
    ).strip()


    if not title:
        return None


    if not filename:
        return None


    if not SAFE_FILENAME.fullmatch(
        filename
    ):
        return None


    return {
        "title": title,
        "author": author,
        "date": date,
        "file": filename,
    }


def read_posts():

    posts = []


    if not INDEX_FILE.exists():
        return posts


    try:

        with INDEX_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            for line in file:

                line = line.strip()


                if not line:
                    continue


                try:

                    post = json.loads(
                        line
                    )

                except json.JSONDecodeError as error:

                    print(
                        "Skipping invalid JSONL line:",
                        error,
                    )

                    continue


                post = normalize_post(
                    post
                )


                if post is not None:

                    posts.append(
                        post
                    )

    except OSError as error:

        print(
            "Failed reading posts index:",
            error,
        )

        return []


    posts.sort(
        key=lambda post: str(
            post.get(
                "date",
                "",
            )
        ),
        reverse=True,
    )


    return posts


def write_posts(posts):

    POSTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    fd, temp_name = tempfile.mkstemp(
        prefix="index-",
        suffix=".tmp",
        dir=str(POSTS_DIR),
    )


    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:

            for post in posts:

                normalized = normalize_post(
                    post
                )


                if normalized is None:
                    continue


                file.write(
                    json.dumps(
                        normalized,
                        ensure_ascii=False,
                    )
                    + "\n"
                )


            file.flush()

            os.fsync(
                file.fileno()
            )


        os.replace(
            temp_name,
            INDEX_FILE,
        )

    except Exception:

        try:
            os.unlink(
                temp_name
            )
        except OSError:
            pass

        raise


@app.get("/")
def index():

    return render_template(
        "index.html"
    )


@app.get("/api/posts")
def posts_api():

    return jsonify({
        "ok": True,
        "posts": read_posts(),
    })


@app.get("/posts/<filename>")
def get_post(filename):

    if not SAFE_FILENAME.fullmatch(
        filename
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid filename.",
        }), 400


    target = (
        POSTS_DIR /
        filename
    ).resolve()


    root = POSTS_DIR.resolve()


    if target.parent != root:

        return jsonify({
            "ok": False,
            "error": "Invalid post path.",
        }), 400


    if not target.is_file():

        return jsonify({
            "ok": False,
            "error": "Post not found.",
        }), 404


    response = send_from_directory(
        POSTS_DIR,
        filename,
        mimetype="text/markdown",
    )


    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate"
    )


    return response


@app.get("/api/config")
def public_config():

    return jsonify({
        "ok": True,
        "macosOnly": MACOS_ONLY,
    })


@app.get("/api/auth/status")
def auth_status():

    return jsonify({
        "ok": True,
        "authenticated":
            is_authenticated(),
    })


@app.post("/api/auth")
def authenticate():

    data = request.get_json(
        silent=True
    ) or {}


    if not isinstance(
        data,
        dict,
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid request.",
        }), 400


    phrase = str(
        data.get(
            "phrase",
            "",
        )
    )


    if not PUBLISH_PHRASE:

        return jsonify({
            "ok": False,
            "error":
                "Server authentication is not configured.",
        }), 500


    if (
        MACOS_ONLY
        and
        not is_mac_request()
    ):

        return jsonify({
            "ok": False,
            "error":
                "Writing access is limited to macOS.",
        }), 403


    if not hmac.compare_digest(
        phrase,
        PUBLISH_PHRASE,
    ):

        return jsonify({
            "ok": False,
            "error":
                "Incorrect publishing phrase.",
        }), 403


    session.clear()

    session.permanent = True

    session[
        "writer_authenticated"
    ] = True


    return jsonify({
        "ok": True,
        "authenticated": True,
    })


@app.post("/api/logout")
def logout():

    session.clear()


    return jsonify({
        "ok": True,
    })


@app.post("/api/publish")
def publish():

    if not is_authenticated():

        return jsonify({
            "ok": False,
            "error":
                "Authentication required.",
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    if not isinstance(
        data,
        dict,
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid request.",
        }), 400


    title = str(
        data.get(
            "title",
            "",
        )
    ).strip()


    author = str(
        data.get(
            "author",
            "",
        )
    ).strip()


    date = str(
        data.get(
            "date",
            "",
        )
    ).strip()


    filename = str(
        data.get(
            "file",
            "",
        )
    ).strip()


    markdown = str(
        data.get(
            "markdown",
            "",
        )
    )


    if not title:

        return jsonify({
            "ok": False,
            "error": "Title required.",
        }), 400


    if not author:

        return jsonify({
            "ok": False,
            "error": "Author required.",
        }), 400


    if not date:

        return jsonify({
            "ok": False,
            "error": "Date required.",
        }), 400


    if not filename:

        return jsonify({
            "ok": False,
            "error":
                "Filename required.",
        }), 400


    if not markdown.strip():

        return jsonify({
            "ok": False,
            "error":
                "Article cannot be empty.",
        }), 400


    if len(title) > MAX_TITLE_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Title is too long.",
        }), 400


    if len(author) > MAX_AUTHOR_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Author is too long.",
        }), 400


    if len(markdown) > MAX_MARKDOWN_LENGTH:

        return jsonify({
            "ok": False,
            "error":
                "Article is too large.",
        }), 413


    if not SAFE_FILENAME.fullmatch(
        filename
    ):

        return jsonify({
            "ok": False,
            "error":
                "Invalid filename.",
        }), 400


    try:

        datetime.strptime(
            date,
            "%Y-%m-%d",
        )

    except ValueError:

        return jsonify({
            "ok": False,
            "error":
                "Date must use YYYY-MM-DD.",
        }), 400


    root = POSTS_DIR.resolve()


    target = (
        POSTS_DIR /
        filename
    ).resolve()


    if target.parent != root:

        return jsonify({
            "ok": False,
            "error":
                "Invalid post path.",
        }), 400


    entry = {
        "title": title,
        "author": author,
        "date": date,
        "file": filename,
    }


    posts = read_posts()


    replaced = False


    for index, post in enumerate(
        posts
    ):

        if (
            post.get("file")
            ==
            filename
        ):

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
                "",
            )
        ),
        reverse=True,
    )


    old_markdown = None

    existed = target.exists()


    if existed:

        try:

            old_markdown = (
                target.read_text(
                    encoding="utf-8"
                )
            )

        except OSError:
            old_markdown = None


    try:

        target.write_text(
            markdown,
            encoding="utf-8",
        )

    except OSError as error:

        print(
            "Failed writing post:",
            error,
        )


        return jsonify({
            "ok": False,
            "error":
                "Could not write post.",
        }), 500


    try:

        write_posts(
            posts
        )

    except OSError as error:

        print(
            "Failed writing index:",
            error,
        )


        try:

            if (
                existed
                and
                old_markdown is not None
            ):

                target.write_text(
                    old_markdown,
                    encoding="utf-8",
                )

            elif target.exists():

                target.unlink()

        except OSError as rollback_error:

            print(
                "Rollback failed:",
                rollback_error,
            )


        return jsonify({
            "ok": False,
            "error":
                "Post index update failed.",
        }), 500


    return jsonify({
        "ok": True,
        "post": entry,
    })


@app.delete("/api/posts/<filename>")
def delete_post(filename):

    if not is_authenticated():

        return jsonify({
            "ok": False,
            "error":
                "Authentication required.",
        }), 401


    if not SAFE_FILENAME.fullmatch(
        filename
    ):

        return jsonify({
            "ok": False,
            "error":
                "Invalid filename.",
        }), 400


    root = POSTS_DIR.resolve()


    target = (
        POSTS_DIR /
        filename
    ).resolve()


    if target.parent != root:

        return jsonify({
            "ok": False,
            "error":
                "Invalid post path.",
        }), 400


    posts = read_posts()


    existing = next(
        (
            post
            for post in posts
            if post.get("file")
            == filename
        ),
        None,
    )


    if existing is None:

        return jsonify({
            "ok": False,
            "error":
                "Article not found.",
        }), 404


    remaining = [
        post
        for post in posts
        if post.get("file")
        != filename
    ]


    previous_markdown = None


    if target.exists():

        try:

            previous_markdown = (
                target.read_text(
                    encoding="utf-8"
                )
            )

        except OSError:
            previous_markdown = None


    try:

        if target.exists():

            target.unlink()


        write_posts(
            remaining
        )

    except OSError as error:

        print(
            "Failed deleting article:",
            error,
        )


        if (
            previous_markdown is not None
            and
            not target.exists()
        ):

            try:

                target.write_text(
                    previous_markdown,
                    encoding="utf-8",
                )

            except OSError as rollback_error:

                print(
                    "Delete rollback failed:",
                    rollback_error,
                )


        return jsonify({
            "ok": False,
            "error":
                "Could not delete article.",
        }), 500


    return jsonify({
        "ok": True,
        "deleted": filename,
    })


@app.after_request
def security_headers(response):

    is_chat_path = request.path.startswith(
        "/chat"
    )


    camera_policy = (
        "camera=(self), "
        if is_chat_path
        else "camera=(), "
    )


    image_policy = (
        "img-src 'self' data: blob:; "
        if is_chat_path
        else "img-src 'self' data:; "
    )

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
        camera_policy
        +
        "microphone=(), "
        "geolocation=()"
    )


    response.headers[
        "Content-Security-Policy"
    ] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' "
        "'unsafe-inline'; "
        + image_policy
        +
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none';"
    )


    if (
        request.path.startswith("/api/")
        or request.path.startswith("/chat/api/")
    ):

        response.headers[
            "Cache-Control"
        ] = (
            "no-store, "
            "no-cache, "
            "must-revalidate"
        )


    return response


@app.errorhandler(404)
def not_found(error):

    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "error":
                "Endpoint not found.",
        }), 404


    return "Not found", 404


@app.errorhandler(405)
def method_not_allowed(error):

    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "error":
                "Method not allowed.",
        }), 405


    return "Method not allowed", 405


@app.errorhandler(413)
def too_large(error):

    return jsonify({
        "ok": False,
        "error":
            "Request is too large.",
    }), 413


@app.errorhandler(500)
def server_error(error):

    print(
        "Internal server error:",
        error,
    )


    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "error":
                "Internal server error.",
        }), 500


    return (
        "Internal server error",
        500,
    )


if __name__ == "__main__":

    print(
        f"Posts directory: {POSTS_DIR}"
    )

    print(
        "Publish phrase configured: "
        f"{bool(PUBLISH_PHRASE)}"
    )

    print(
        "macOS-only writing: "
        f"{MACOS_ONLY}"
    )

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )
