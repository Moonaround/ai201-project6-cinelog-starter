"""Tests for the watchlist service."""

from datetime import datetime, timedelta, timezone

import pytest

from app import create_app, db
from models import Film, User, WatchlistEntry
from services.collection_service import FilmNotFoundError
from services.watchlist_service import (
    AlreadyInWatchlistError,
    NotInWatchlistError,
    add_to_watchlist,
    get_watchlist,
    remove_from_watchlist,
)


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


@pytest.fixture
def sample_film(app):
    """Create a film for watchlist tests."""
    with app.app_context():
        film = Film(title="Moonlight", year=2016, genre="Drama")
        db.session.add(film)
        db.session.commit()
        return film.id


def test_add_to_watchlist_creates_private_entry(app, sample_user, sample_film):
    """An explicit visibility choice should be stored on the new entry."""
    with app.app_context():
        entry = add_to_watchlist(
            user_id=sample_user,
            film_id=sample_film,
            public=False,
        )

        assert entry.user_id == sample_user
        assert entry.film_id == sample_film
        assert entry.public is False


def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """The same user and film combination may only be saved once."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """Adding a missing film should raise FilmNotFoundError."""
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


def test_remove_from_watchlist_deletes_entry(app, sample_user, sample_film):
    """Removing a saved film should delete its watchlist entry."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert remove_from_watchlist(sample_user, sample_film) is True
        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first() is None


def test_remove_from_watchlist_missing_entry_raises(app, sample_user, sample_film):
    """Removing an unsaved film should report a domain-specific error."""
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(sample_user, sample_film)


def test_get_watchlist_returns_newest_first(app, sample_user):
    """Recent discoveries should appear before older watchlist entries."""
    with app.app_context():
        older_film = Film(title="Alien", year=1979, genre="Horror")
        newer_film = Film(title="Arrival", year=2016, genre="Sci-Fi")
        db.session.add_all([older_film, newer_film])
        db.session.commit()

        older_entry = WatchlistEntry(
            user_id=sample_user,
            film_id=older_film.id,
            date_added=datetime.now(timezone.utc) - timedelta(days=5),
        )
        newer_entry = WatchlistEntry(
            user_id=sample_user,
            film_id=newer_film.id,
            date_added=datetime.now(timezone.utc),
        )
        db.session.add_all([older_entry, newer_entry])
        db.session.commit()

        watchlist = get_watchlist(sample_user)

        assert [film["title"] for film in watchlist] == ["Arrival", "Alien"]


def test_watchlist_endpoints_support_visibility_and_removal(
    app, sample_user, sample_film
):
    """The API should persist visibility and remove the same entry."""
    client = app.test_client()

    add_response = client.post(
        f"/watchlist/{sample_user}/add",
        json={"film_id": sample_film, "public": False},
    )
    assert add_response.status_code == 201
    assert add_response.get_json()["public"] is False

    remove_response = client.delete(
        f"/watchlist/{sample_user}/remove",
        json={"film_id": sample_film},
    )
    assert remove_response.status_code == 200


def test_add_watchlist_endpoint_maps_validation_errors(
    app, sample_user, sample_film
):
    """Expected domain failures should produce useful client responses."""
    client = app.test_client()
    endpoint = f"/watchlist/{sample_user}/add"

    assert client.post(
        endpoint, json={"film_id": sample_film, "public": "yes"}
    ).status_code == 400

    assert client.post(endpoint, json={"film_id": sample_film}).status_code == 201
    assert client.post(endpoint, json={"film_id": sample_film}).status_code == 409

    missing_film_id = "00000000-0000-0000-0000-000000000000"
    assert client.post(
        endpoint, json={"film_id": missing_film_id}
    ).status_code == 404
