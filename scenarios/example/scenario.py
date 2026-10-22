"""A small PUBLIC example scenario so the harness is runnable out of the box.

Task family: pick a meeting room for a request, honouring the user's stored
preferences and the live room-availability table. Copy this file to your own
(private) directory and edit it to define a new task.
"""
from memory_experiment.core.types import EvalCase, Fact, Scenario, Table

TABLES = [
    Table("rooms", "id text primary key, name text, floor int, capacity int, has_whiteboard boolean", "Meeting rooms in the office."),
    Table("bookings", "id serial primary key, room_id text, day date, start_hour int, end_hour int", "Existing bookings; a room is busy for [start_hour, end_hour)."),
]

ROOMS = [
    {"id": "r1", "name": "Aspen", "floor": 2, "capacity": 4, "has_whiteboard": True},
    {"id": "r2", "name": "Birch", "floor": 2, "capacity": 8, "has_whiteboard": False},
    {"id": "r3", "name": "Cedar", "floor": 5, "capacity": 6, "has_whiteboard": True},
]

FACTS = [
    Fact("u1", "meetings", "Always wants a whiteboard in the room."),
    Fact("u1", "meetings", "Prefers rooms on floor 2; will accept other floors only if nothing on floor 2 is free."),
    Fact("u2", "meetings", "Hates whiteboards; wants the biggest room available."),  # another user: must be ignored
]

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"room_id": {"type": ["string", "null"]}, "reason": {"type": "string"}},
    "required": ["room_id", "reason"],
}

CASES = [
    EvalCase("floor2_free", "Book me a room for 3 people on 2026-03-02 from 10 to 11.", {"rooms": ROOMS, "bookings": []}, FACTS, {"room_id": "r1"}, user_id="u1"),
    EvalCase("floor2_busy", "Book me a room for 3 people on 2026-03-02 from 10 to 11.", {"rooms": ROOMS, "bookings": [{"room_id": "r1", "day": "2026-03-02", "start_hour": 9, "end_hour": 12}]}, FACTS, {"room_id": "r3"}, user_id="u1"),
    EvalCase("all_busy", "Book me a room for 3 people on 2026-03-02 from 10 to 11.", {"rooms": ROOMS, "bookings": [{"room_id": "r1", "day": "2026-03-02", "start_hour": 9, "end_hour": 12}, {"room_id": "r3", "day": "2026-03-02", "start_hour": 10, "end_hour": 11}]}, FACTS, {"room_id": None}, user_id="u1"),
]

SCENARIO = Scenario(
    name="example-rooms",
    task_prompt="Choose the single best meeting room for the user's request, applying their stored preferences to the live rooms/bookings data. If no room satisfies the hard requirements, answer with room_id null.",
    tables=TABLES,
    answer_schema=ANSWER_SCHEMA,
    cases=CASES,
)
