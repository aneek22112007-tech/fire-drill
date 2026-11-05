"""M1: post a message, read it back, check ordering."""

from firedrill.adapters.local import LocalAdapter


def test_post_read_and_order(tmp_path):
    bus = LocalAdapter(tmp_path / "room.db")
    first = bus.post(
        author="change-agent",
        role="change-agent",
        body="one",
        ts="2026-11-05T15:00:03Z",
    )
    second = bus.post(
        author="avery",
        role="human",
        body="two",
        thread_id=first.id,
        ts="2026-11-05T15:00:01Z",
    )
    third = bus.post(
        author="auditor",
        role="auditor",
        body="three",
        channel="dm:avery",
        ts="2026-11-05T15:00:02Z",
    )

    room = bus.read_room()
    assert [message.body for message in room] == ["one", "two"]
    assert [message.seq for message in room] == [1, 2]
    assert room[0].author == "change-agent"
    assert room[0].role == "change-agent"
    assert room[0].ts == "2026-11-05T15:00:03Z"
    assert room[1].thread_id == first.id
    assert room[1].role == "human"

    private = bus.read_channel("dm:avery")
    assert [message.id for message in private] == [third.id]
    assert third.body not in {message.body for message in room}

    bus.add_reaction(message_id=first.id, user="avery", emoji="white_check_mark")
    assert bus.reactions_for(first.id) == [("avery", "white_check_mark")]
    bus.close()
