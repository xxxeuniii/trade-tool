import json
import os
import re
from contextlib import closing
from datetime import date, timedelta
from typing import Any, Literal

import holidays
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Trade Tool API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://127.0.0.1:8081", "http://106.53.77.119"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def connect():
    """Open the trade-tool PostgreSQL connection from server environment variables."""
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "host.docker.internal"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DATABASE", "stock_data"),
        user=os.getenv("PG_USER", "trade_agent"),
        password=os.environ["PG_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def init_db():
    """Create tables owned by trade-tool when the service starts."""
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_tool_attendance (
                attendance_date TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('present', 'leave', 'absent')),
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS trade_tool_history (
                history_id TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cursor.execute(
            """
            ALTER TABLE trade_tool_attendance
                DROP CONSTRAINT IF EXISTS trade_tool_attendance_status_check;
            ALTER TABLE trade_tool_attendance
                ADD CONSTRAINT trade_tool_attendance_status_check
                CHECK (status IN ('present', 'leave', 'absent'));
            """
        )
        cursor.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('public.attendance_record') IS NOT NULL THEN
                    INSERT INTO trade_tool_attendance (attendance_date, status, updated_at)
                    SELECT attendance_date, status, updated_at FROM attendance_record
                    WHERE status IN ('present', 'leave', 'absent')
                    ON CONFLICT (attendance_date) DO NOTHING;
                END IF;
                IF to_regclass('public.trade_history') IS NOT NULL THEN
                    INSERT INTO trade_tool_history (history_id, payload, created_at, updated_at)
                    SELECT history_id, payload, created_at, updated_at FROM trade_history
                    ON CONFLICT (history_id) DO NOTHING;
                END IF;
            END $$;
            """
        )
        connection.commit()


@app.on_event("startup")
def startup():
    """Initialize trade-tool database tables."""
    init_db()


class AttendancePayload(BaseModel):
    date: str
    status: Literal["present", "leave", "absent"] | None = None


class HistoryPayload(BaseModel):
    record: dict[str, Any]


MARKET_CALENDARS = {
    "china": ("financial", "XSHG"),
    "japan": ("financial", "XJPX"),
    "korea": ("country", "KR"),
    "us": ("financial", "XNYS"),
    "europe": ("financial", "XETR"),
}


def dates_in_year(year: int):
    current = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    while current < end:
        yield current
        current += timedelta(days=1)


def short_china_holiday_name(name: str) -> str:
    """Convert the library's official holiday name to a compact calendar label."""
    labels = (
        (("春节", "Chinese New Year"), "春节"),
        (("除夕", "New Year's Eve"), "除夕"),
        (("元旦", "New Year's Day"), "元旦"),
        (("清明", "Tomb-Sweeping"), "清明"),
        (("劳动", "Labor Day"), "五一"),
        (("端午", "Dragon Boat"), "端午"),
        (("中秋", "Mid-Autumn"), "中秋"),
        (("国庆", "National Day"), "国庆"),
    )
    for needles, label in labels:
        if any(needle in name for needle in needles):
            return label
    return "假期"


@app.get("/api/calendars/{year}")
def get_calendars(year: int):
    """Return Chinese statutory holidays and exchange holiday dates for one year."""
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="year must be between 2000 and 2100")

    china = holidays.country_holidays("CN", years=[year], language="zh_CN")
    attendance_holiday_dates = {
        day for day in china if day.year == year and not china.is_working_day(day)
    }
    # The library lists statutory/transfer dates but omits ordinary weekend days
    # inside the same announced break. Expand only weekends touching that break.
    changed = True
    while changed:
        changed = False
        for current in dates_in_year(year):
            if current.weekday() < 5 or china.is_working_day(current) or current in attendance_holiday_dates:
                continue
            if current - timedelta(days=1) in attendance_holiday_dates or current + timedelta(days=1) in attendance_holiday_dates:
                attendance_holiday_dates.add(current)
                changed = True

    attendance_holidays = []
    adjusted_workdays = []
    for current in dates_in_year(year):
        key = current.isoformat()
        if current in attendance_holiday_dates:
            attendance_holidays.append(key)

    holiday_names = {}
    ordered_holidays = sorted(attendance_holiday_dates)
    block_start = 0
    while block_start < len(ordered_holidays):
        block_end = block_start + 1
        while block_end < len(ordered_holidays) and ordered_holidays[block_end] - ordered_holidays[block_end - 1] == timedelta(days=1):
            block_end += 1
        block = ordered_holidays[block_start:block_end]
        official_names = " · ".join(china.get(day) for day in block if china.get(day))
        if official_names:
            holiday_names[block[0].isoformat()] = short_china_holiday_name(official_names)
        block_start = block_end

    market_holidays = {}
    for market_id, (calendar_type, code) in MARKET_CALENDARS.items():
        calendar = (
            holidays.financial_holidays(code, years=[year])
            if calendar_type == "financial"
            else holidays.country_holidays(code, years=[year])
        )
        market_holidays[market_id] = sorted(day.isoformat() for day in calendar)

    return {
        "success": True,
        "data": {
            "year": year,
            "attendance": {
                "holidays": attendance_holidays,
                "adjustedWorkdays": adjusted_workdays,
                "holidayNames": holiday_names,
            },
            "markets": market_holidays,
        },
    }


@app.get("/api/health")
def health():
    """Report service and database health."""
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
    return {"success": True, "data": "ok"}


@app.get("/api/attendance/{month}")
def get_attendance(month: str):
    """Read one month of attendance records."""
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(status_code=400, detail="month must use YYYY-MM")
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT attendance_date, status FROM trade_tool_attendance WHERE attendance_date LIKE %s ORDER BY attendance_date",
            (f"{month}-%",),
        )
        rows = cursor.fetchall()
    return {"success": True, "data": {row["attendance_date"]: row["status"] for row in rows}}


@app.post("/api/attendance")
def update_attendance(payload: AttendancePayload):
    """Create, update, or delete one attendance record."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload.date):
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD")
    with closing(connect()) as connection, connection.cursor() as cursor:
        if payload.status is None:
            cursor.execute("DELETE FROM trade_tool_attendance WHERE attendance_date = %s", (payload.date,))
        else:
            cursor.execute(
                """INSERT INTO trade_tool_attendance (attendance_date, status, updated_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP)
                   ON CONFLICT(attendance_date) DO UPDATE SET status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP""",
                (payload.date, payload.status),
            )
        connection.commit()
    return {"success": True, "data": payload.model_dump()}


@app.get("/api/trade-history")
def get_trade_history():
    """Read all trade calculator history from PostgreSQL."""
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM trade_tool_history ORDER BY created_at DESC, history_id DESC")
        rows = cursor.fetchall()
    return {"success": True, "data": [row["payload"] for row in rows]}


@app.post("/api/trade-history")
def save_trade_history(payload: HistoryPayload):
    """Create or update one trade calculator history record."""
    history_id = payload.record.get("id")
    if not history_id:
        raise HTTPException(status_code=400, detail="record.id is required")
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO trade_tool_history (history_id, payload, updated_at)
               VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
               ON CONFLICT(history_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = CURRENT_TIMESTAMP""",
            (str(history_id), json.dumps(payload.record, ensure_ascii=False)),
        )
        connection.commit()
    return {"success": True, "data": payload.record}


@app.post("/api/trade-history/clear")
def clear_trade_history():
    """Delete all trade calculator history records."""
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM trade_tool_history")
        connection.commit()
    return {"success": True, "data": []}
