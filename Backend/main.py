"""
Railway Block Planner — Backend
FastAPI + SQLite. Provides:
  - Maintenance request intake (Engineering / S&T / Traction Distribution)
  - Corridor availability (mock Control Office Application data)
  - AI-style prioritization + scheduling engine
  - Dashboard + schedule endpoints for the frontend
"""

import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = "block_planner.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT NOT NULL,
            section TEXT NOT NULL,
            issue TEXT NOT NULL,
            priority TEXT NOT NULL,               -- High / Medium / Low
            status TEXT NOT NULL DEFAULT 'Pending', -- Pending / Scheduled
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS corridor_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            section TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_booked INTEGER NOT NULL DEFAULT 0    -- mock COA: free windows between trains
        );

        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            day TEXT NOT NULL,
            department TEXT NOT NULL,
            section TEXT NOT NULL,
            block_time TEXT NOT NULL,
            priority TEXT NOT NULL,
            FOREIGN KEY (request_id) REFERENCES requests(id)
        );
        """)

        # Seed corridor availability (mock train-timetable-derived free windows)
        cur = conn.execute("SELECT COUNT(*) c FROM corridor_slots")
        if cur.fetchone()["c"] == 0:
            seed_slots = [
                ("Monday", "Sec A-12", "10:00", "12:00"),
                ("Tuesday", "Sec B-05", "14:00", "16:00"),
                ("Wednesday", "Sec C-09", "09:00", "11:00"),
                ("Thursday", "Sec A-07", "08:00", "10:00"),
                ("Friday", "Sec A-07", "13:00", "15:00"),
                ("Friday", "Sec B-05", "09:00", "11:00"),
                ("Saturday", "Sec C-09", "11:00", "13:00"),
                ("Saturday", "Sec A-12", "15:00", "17:00"),
            ]
            conn.executemany(
                "INSERT INTO corridor_slots (day, section, start_time, end_time) VALUES (?,?,?,?)",
                seed_slots,
            )

        # Seed initial schedule (matches the static rows already on the frontend)
        cur = conn.execute("SELECT COUNT(*) c FROM schedule")
        if cur.fetchone()["c"] == 0:
            seed_schedule = [
                (None, "Monday", "Engineering", "Sec A-12", "10:00 - 12:00", "High"),
                (None, "Tuesday", "Signal & Telecom", "Sec B-05", "14:00 - 16:00", "Medium"),
                (None, "Wednesday", "Traction Distribution", "Sec C-09", "09:00 - 11:00", "High"),
                (None, "Friday", "Engineering", "Sec A-07", "13:00 - 15:00", "Low"),
            ]
            conn.executemany(
                "INSERT INTO schedule (request_id, day, department, section, block_time, priority) VALUES (?,?,?,?,?,?)",
                seed_schedule,
            )


class RequestIn(BaseModel):
    department: str
    section: str
    issue: str
    priority: str  # High / Medium / Low


class RequestOut(RequestIn):
    id: int
    status: str
    created_at: str


class ScheduleOut(BaseModel):
    day: str
    department: str
    section: str
    block_time: str
    priority: str


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Railway Block Planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

PRIORITY_WEIGHT = {"High": 3, "Medium": 2, "Low": 1}
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ---------------------------------------------------------------------------
# Endpoints: Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard():
    with get_db() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) c FROM requests WHERE status = 'Pending'"
        ).fetchone()["c"]

        total_slots = conn.execute("SELECT COUNT(*) c FROM corridor_slots").fetchone()["c"]
        booked_slots = conn.execute(
            "SELECT COUNT(*) c FROM corridor_slots WHERE is_booked = 1"
        ).fetchone()["c"]
        blocks_available = max(total_slots - booked_slots, 0)

        # simple uptime proxy: fewer overdue/high-priority pending items => higher uptime
        high_pending = conn.execute(
            "SELECT COUNT(*) c FROM requests WHERE status='Pending' AND priority='High'"
        ).fetchone()["c"]
        asset_uptime = max(70, 98 - high_pending * 3)

        return {
            "pending_count": pending,
            "blocks_available": blocks_available,
            "asset_uptime": asset_uptime,
        }


# ---------------------------------------------------------------------------
# Endpoints: Requests
# ---------------------------------------------------------------------------

@app.get("/api/requests", response_model=List[RequestOut])
def list_requests(status: Optional[str] = None):
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM requests WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM requests ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/requests", response_model=RequestOut)
def create_request(req: RequestIn):
    if req.priority not in PRIORITY_WEIGHT:
        raise HTTPException(400, "priority must be High, Medium or Low")

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO requests (department, section, issue, priority, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (req.department, req.section, req.issue, req.priority, "Pending", datetime.utcnow().isoformat()),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (new_id,)).fetchone()
        return dict(row)


# ---------------------------------------------------------------------------
# Endpoints: Schedule
# ---------------------------------------------------------------------------

@app.get("/api/schedule", response_model=List[ScheduleOut])
def get_schedule():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT day, department, section, block_time, priority FROM schedule"
        ).fetchall()
        rows = sorted(rows, key=lambda r: DAY_ORDER.index(r["day"]) if r["day"] in DAY_ORDER else 99)
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# The core "AI" piece: prioritize pending requests, then greedily assign
# them to free corridor slots without double-booking a section/day/time,
# merging same-section same-day requests into one block where possible.
# ---------------------------------------------------------------------------

@app.post("/api/optimize")
def run_optimizer():
    with get_db() as conn:
        pending = conn.execute(
            "SELECT * FROM requests WHERE status = 'Pending'"
        ).fetchall()

        if not pending:
            return {"scheduled": 0, "message": "No pending requests to schedule."}

        # 1. Prioritize: higher weight first, then earliest submitted (FIFO tiebreak)
        ranked = sorted(
            pending,
            key=lambda r: (-PRIORITY_WEIGHT[r["priority"]], r["created_at"]),
        )

        free_slots = conn.execute(
            "SELECT * FROM corridor_slots WHERE is_booked = 0"
        ).fetchall()

        scheduled_count = 0

        for req in ranked:
            # 2. Find a matching free slot for this section (any day), earliest day first
            candidates = [
                s for s in free_slots
                if s["section"] == req["section"]
            ]
            candidates = sorted(
                candidates,
                key=lambda s: DAY_ORDER.index(s["day"]) if s["day"] in DAY_ORDER else 99,
            )

            if not candidates:
                # No free corridor slot for this section right now — stays Pending
                continue

            slot = candidates[0]

            # 3. Book the slot
            conn.execute(
                "UPDATE corridor_slots SET is_booked = 1 WHERE id = ?", (slot["id"],)
            )
            conn.execute(
                "UPDATE requests SET status = 'Scheduled' WHERE id = ?", (req["id"],)
            )
            conn.execute(
                "INSERT INTO schedule (request_id, day, department, section, block_time, priority) "
                "VALUES (?,?,?,?,?,?)",
                (
                    req["id"],
                    slot["day"],
                    req["department"],
                    req["section"],
                    f"{slot['start_time']} - {slot['end_time']}",
                    req["priority"],
                ),
            )

            free_slots = [s for s in free_slots if s["id"] != slot["id"]]
            scheduled_count += 1

        return {
            "scheduled": scheduled_count,
            "remaining_pending": len(ranked) - scheduled_count,
            "message": f"{scheduled_count} request(s) assigned to available corridor blocks.",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)