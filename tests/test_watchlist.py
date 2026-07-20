"""Tests for the watchlist service."""

import pytest

from app import create_app, db
from models import User
from services.collection_service import FilmNotFoundError
from services.watchlist_service import add_to_watchlist


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """Create a user for watchlist tests."""
    with app.app_context():
        user = User(username="watcher", email="watcher@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """Adding a missing film should raise FilmNotFoundError."""
    with app.app_context():
        fake_film_id = 999999

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)
