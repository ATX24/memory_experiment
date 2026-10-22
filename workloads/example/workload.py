"""A small PUBLIC example workload so the harness runs out of the box: pick a meeting
room honouring the principal's stored preferences (memory state) and the live
rooms/bookings tables (data state). Copy this file to a private directory to define
a real workload."""
from memory_experiment.eval.graders import ExactMatch
from memory_experiment.eval.types import Case, Fact, Table, Workload

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
    Fact("u1", "meetings", "Prefers rooms on floor 2; accepts other floors only if nothing on floor 2 is free."),
    Fact("u2", "meetings", "Hates whiteboards; wants the biggest room available."),  # another principal: must be ignored
]
P = "Book me a room for 3 people on 2026-03-02 from 10 to 11."
WORKLOAD = Workload(
    name="example-rooms",
    description="toy workload: room choice from preferences + availability",
    task_prompt="Choose the single best meeting room for the request, applying the principal's stored preferences to the live rooms/bookings data. If no room satisfies the hard requirements, answer room_id null.",
    tables=TABLES,
    rows={"rooms": ROOMS},
    facts=FACTS,
    answer_schema={"type": "object", "properties": {"room_id": {"type": ["string", "null"]}, "reason": {"type": "string"}}, "required": ["room_id", "reason"]},
    cases=[
        Case("floor2_free", P, "u1", {"room_id": "r1"}),
        Case("floor2_busy", P, "u1", {"room_id": "r3"}, rows={"bookings": [{"room_id": "r1", "day": "2026-03-02", "start_hour": 9, "end_hour": 12}]}),
        Case("all_busy", P, "u1", {"room_id": None}, rows={"bookings": [{"room_id": "r1", "day": "2026-03-02", "start_hour": 9, "end_hour": 12}, {"room_id": "r3", "day": "2026-03-02", "start_hour": 10, "end_hour": 11}]}),
    ],
    grader=ExactMatch(["room_id"]),
)
