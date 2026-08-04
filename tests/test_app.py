import asyncio
import json

import pytest

from theoremsmith import events


@pytest.fixture(autouse=True)
def loop():
    running = asyncio.new_event_loop()
    events.bind_loop(running)
    yield running
    running.close()


def test_a_late_subscriber_still_gets_everything_that_happened(loop):
    events.emit("r1", "log", text="first")
    events.emit("r1", "log", text="second")
    replay = events.history("r1")
    assert [e["text"] for e in replay] == ["first", "second"]
    assert [e["seq"] for e in replay] == [1, 2]


def test_history_can_resume_from_a_sequence_number():
    events.emit("r2", "log", text="a")
    events.emit("r2", "log", text="b")
    assert [e["text"] for e in events.history("r2", after=1)] == ["b"]


def test_two_subscribers_both_receive_a_later_event(loop):
    async def scenario():
        one, two = events.subscribe("r3"), events.subscribe("r3")
        events.emit("r3", "log", text="broadcast")
        await asyncio.sleep(0)
        try:
            return one.get_nowait()["text"], two.get_nowait()["text"]
        finally:
            events.unsubscribe("r3", one)
            events.unsubscribe("r3", two)

    assert loop.run_until_complete(scenario()) == ("broadcast", "broadcast")


def test_a_full_subscriber_queue_never_blocks_the_worker(loop):
    queue = events.subscribe("r4")
    for i in range(queue.maxsize + 50):
        events.emit("r4", "log", text=str(i))
    loop.run_until_complete(asyncio.sleep(0))
    assert queue.qsize() <= queue.maxsize
    events.unsubscribe("r4", queue)


def test_emitting_without_a_bound_loop_still_records_history(monkeypatch):
    monkeypatch.setattr(events, "_loop", None)
    events.emit("r5", "log", text="offline")
    assert [e["text"] for e in events.history("r5")] == ["offline"]


def test_the_sse_frame_carries_the_id_and_the_json():
    frame = events.sse({"seq": 7, "kind": "log", "text": "x"})
    assert frame.startswith("id: 7\ndata: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame.split("data: ", 1)[1])["text"] == "x"
