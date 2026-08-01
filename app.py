"""Compatibility launcher and WSGI entry point.

Use ``python app.py`` for local development or ``app:app`` with a WSGI server.
"""

from podcast_cutter import create_app

app = create_app()


if __name__ == "__main__":
    from podcast_cutter.cli import main

    main()

