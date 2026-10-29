import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import frisian_shorts
from frisian_shorts import (
    END_LABEL,
    SQ,
    boards,
    jumped,
    next_publish_time,
    next_puzzle,
    parse_fen,
    read_uploaded,
    square_xy,
)


def test_parse_fen():
    assert parse_fen("B:WP16,31:B15,K46,G3:H0:F36:+0+0") == {
        16: ("W", "P"),
        31: ("W", "M"),
        15: ("B", "M"),
        46: ("B", "K"),
        3: ("B", "G"),
    }
    assert parse_fen("W:W:B15:H0:F1") == {15: ("B", "M")}


def test_square_xy():
    assert square_xy(1, False) == (SQ, 0)
    assert square_xy(46, False) == (0, 9 * SQ)
    assert square_xy(46, True) == (9 * SQ, 0)
    assert square_xy(50, False) == (8 * SQ, 9 * SQ)


def test_jumped():
    assert jumped({21: ("B", "M")}, 16, 27) == 21  # diagonal
    assert jumped({16: ("W", "K")}, 6, 26) == 16  # vertical (Frisian)
    assert jumped({22: ("W", "M")}, 21, 23) == 22  # horizontal (Frisian)
    assert jumped({22: ("W", "M")}, 17, 21) is None  # plain move


def test_board_tags():
    # black plays 18-22, white solves with 27x18
    data = {
        "puzzle": {
            "fen": "B:W27:B18:H0:F1",
            "color": "white",
            "branch": {"uci": "2718", "fen": "B:W18:B:H0:F2", "children": []},
        },
        "history": {"uci": "1822", "fen": "W:W27:B22:H0:F1"},
    }
    yields = list(boards(data))
    assert [tag for _, _, tag, _ in yields if tag] == ["move", "think", "capture"]
    # header labels in order: prompt, the solution move, the end card
    assert [label for _, label, _ in dict.fromkeys(head for *_, head in yields)] == [
        "WHITE TO PLAY",
        "27x18",
        END_LABEL,
    ]


def test_read_uploaded(tmp_path):
    path = tmp_path / "uploaded.txt"
    path.write_text("# header\n\n3\n791  # boring\n  12\n")
    assert read_uploaded(path) == {3, 12, 791}


def test_next_puzzle(monkeypatch):
    fetched = []

    def fake_fetch(pid):
        fetched.append(pid)
        if pid == 2:  # lidraughts doesn't have this one
            raise urllib.error.HTTPError("url", 404, "Not Found", None, None)
        return {"puzzle": {"id": pid}}

    monkeypatch.setattr(frisian_shorts, "fetch_puzzle", fake_fetch)
    assert next_puzzle({1, 3}) == {"puzzle": {"id": 4}}
    assert fetched == [2, 4]


@pytest.mark.parametrize(
    "uci, fen, tags",
    [
        ("4842", "B:W20,42:B14", ["move", "think", "move", "move", "think", "move"]),  # quiet move: countdown
        ("2009", "B:W9,48:B:H0:F3", ["move", "think", "move", "move", "capture"]),  # capture is forced: none
    ],
)
def test_countdown_before_later_quiet_moves(uci, fen, tags):
    # black 5-10, white 25-20, black 10-14, then white's second move under test
    final = {"uci": uci, "fen": fen, "children": []}
    reply = {"uci": "1014", "fen": "W:W20,48:B14:H0:F2", "children": [final]}
    data = {
        "puzzle": {
            "fen": "B:W25,48:B5:H0:F1",
            "color": "white",
            "branch": {"uci": "2520", "fen": "B:W20,48:B10:H0:F2", "children": [reply]},
        },
        "history": {"uci": "0510", "fen": "W:W25,48:B10:H0:F1"},
    }
    assert [tag for _, _, tag, _ in boards(data) if tag] == tags


def test_next_publish_time():
    utc = ZoneInfo("UTC")
    # morning run (07:23 Dutch summer time): same day; evening run: next day; winter time switches the offset
    assert next_publish_time(datetime(2026, 7, 1, 5, 23, tzinfo=utc)).isoformat() == "2026-07-01T18:00:00+02:00"
    assert next_publish_time(datetime(2026, 7, 1, 17, 0, tzinfo=utc)).isoformat() == "2026-07-02T18:00:00+02:00"
    assert next_publish_time(datetime(2026, 12, 1, 6, 23, tzinfo=utc)).isoformat() == "2026-12-01T18:00:00+01:00"
