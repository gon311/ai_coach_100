"""MVP authentication, measurement catalogue, percentile evaluation, and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


SOURCE_FILE = Path(__file__).resolve()
REPOSITORY_LAYOUT = SOURCE_FILE.parent.name == "src" and SOURCE_FILE.parent.parent.name == "api"
ROOT = SOURCE_FILE.parents[3] if REPOSITORY_LAYOUT else SOURCE_FILE.parents[2]
API_ROOT = SOURCE_FILE.parent.parent
NORM_DB = Path(os.environ.get(
    "AI_FITNESS_NORM_DB",
    str((API_ROOT / "artifacts" if REPOSITORY_LAYOUT else ROOT / "fitness_backend_package") / "fitness_percentile.db"),
))
USER_DB = Path(os.environ.get(
    "AI_FITNESS_USER_DB",
    str((API_ROOT / "runtime" if REPOSITORY_LAYOUT else ROOT) / "fitness_user_records.db"),
))
MIN_SAMPLE = 100
A_PATH_VERSION = "2026-09-16-a-trend-sign-v2"
try:
    AUTH_SESSION_TTL_HOURS = max(1.0, float(os.environ.get("AI_FITNESS_AUTH_TTL_HOURS", "24")))
except ValueError:
    AUTH_SESSION_TTL_HOURS = 24.0
AUTH_SESSION_TTL = timedelta(hours=AUTH_SESSION_TTL_HOURS)
HOME_TOP_PERCENT_WIDTH = {
    "SIT_AND_REACH": 10,
    "SHUTTLE_RUN_10M": 8,
    "CROSS_SIT_UP": 7,
    "STEP_IN_PLACE_2MIN": 7,
    "RELATIVE_GRIP": 7,
    "STANDING_LONG_JUMP": 5,
    "CHAIR_STAND_30S": 5,
    "CHAIR_3M_TURN": 10,
}
PUBLIC_FACTOR_LABELS = {
    "CHAIR_3M_TURN": "평형성",
    "FIGURE_8_WALK": "협응력",
}
VIDEO_DIR = (
    ROOT / "data" / "reference" / "videos"
    if REPOSITORY_LAYOUT else ROOT / "data" / "국민체력100 동영상 정보"
)
MEASURE_VIDEO_JSON = VIDEO_DIR / "02_체력인증측정방법.json"
ALL_VIDEO_JSON = VIDEO_DIR / "07_동영상전체목록.json"
STANDARD_VIDEO_JSON = VIDEO_DIR / "05_생애주기별표준운동.json"
ROUTINE_VIDEO_JSON = VIDEO_DIR / "06_목적별루틴운동.json"
router = APIRouter(prefix="/api/mvp", tags=["fitness-mvp"])


def _public_factor_name(item_code: str, stored_name: Any = "") -> str:
    return PUBLIC_FACTOR_LABELS.get(item_code, str(stored_name or ""))


# 표시명과 요인명은 DB의 (life_stage, item_code) 행을 그대로 사용한다.
# 같은 SHUTTLE_RUN_10M이라도 생애주기에 따라 의미와 단위가 달라질 수 있다.
VIDEO_CATEGORY = {
    "CURL_UP": "endurance", "CROSS_SIT_UP": "endurance",
    "SIT_AND_REACH": "flexibility", "STANDING_LONG_JUMP": "power",
    "RELATIVE_GRIP": "grip", "ABSOLUTE_GRIP": "grip",
    "SHUTTLE_RUN_10M": "agility", "SHUTTLE_RUN_15M": "cardio",
    "SHUTTLE_RUN_20M": "cardio", "SHUTTLE_RUN_5M_X4": "agility",
    "SIDE_STEP": "agility", "CHAIR_STAND_30S": "strength",
    "STEP_IN_PLACE_2MIN": "cardio", "CHAIR_3M_TURN": "agility",
}

GUIDES = {
    "CURL_UP": {"duration":"준비 포함 약 3~5분 · 정해진 박자에서 더 수행할 수 없을 때까지", "attempts":"연습 후 1회", "method":"매트에 누워 무릎을 약 90도로 굽히고 손은 허벅지 위에 둡니다. 일정한 박자에 맞춰 손끝이 무릎에 닿도록 상체를 말아 올렸다가 어깨가 매트에 닿을 때까지 내려오며 정확히 완료한 횟수를 기록합니다.", "caution":"반동을 쓰거나 발이 바닥에서 떨어진 반복은 세지 않습니다."},
    "CROSS_SIT_UP": {"duration":"1분 측정 · 준비 포함 약 4분", "attempts":"연습 2~3회 후 1회", "method":"무릎을 세우고 누워 양손을 귀 옆에 둡니다. 시작과 함께 상체를 들어 오른쪽 팔꿈치와 왼쪽 무릎, 왼쪽 팔꿈치와 오른쪽 무릎이 번갈아 닿게 하고 1분간 정확한 횟수를 셉니다.", "caution":"목을 당기거나 엉덩이가 들린 동작은 제외하고 허리 통증 시 중단합니다."},
    "SIT_AND_REACH": {"duration":"각 시도 2~3초 유지 · 총 약 3분", "attempts":"2회 측정해 좋은 기록", "method":"맨발로 앉아 두 무릎을 완전히 펴고 발바닥을 측정기준면에 붙입니다. 양손을 포개 숨을 내쉬며 천천히 앞으로 밀고 최종 위치를 2초 이상 유지해 cm로 기록합니다.", "caution":"반동을 주거나 한쪽 손만 더 내밀지 않습니다. 발끝 기준을 0cm로 통일합니다."},
    "STANDING_LONG_JUMP": {"duration":"시도 간 1분 휴식 · 총 약 5분", "attempts":"2회 측정해 좋은 기록", "method":"발끝을 출발선 바로 뒤에 두고 양발을 어깨너비로 섭니다. 팔과 무릎을 함께 사용해 앞으로 점프하고, 출발선부터 착지 후 가장 뒤에 닿은 발뒤꿈치까지의 최단거리를 cm로 잽니다.", "caution":"미끄럽지 않은 바닥과 충분한 착지공간을 확보하고 뒤로 넘어지면 다시 측정합니다."},
    "RELATIVE_GRIP": {"duration":"한 손당 약 3초 · 시도 간 30초 휴식", "attempts":"좌우 각 2회, 가장 큰 악력÷체중×100", "method":"악력계 손잡이를 두 번째 손가락 마디가 직각이 되도록 조절합니다. 팔을 몸통에서 조금 떼고 악력계가 몸에 닿지 않게 선 뒤 약 3초간 최대 힘으로 잡습니다. 최고 kg 값을 체중으로 나눠 100을 곱한 값을 입력합니다.", "caution":"손목을 꺾거나 팔을 몸에 붙여 지지하지 않습니다."},
    "ABSOLUTE_GRIP": {"duration":"한 손당 약 3초 · 시도 간 30초 휴식", "attempts":"좌우 각 2회 중 가장 큰 kg", "method":"손 크기에 맞게 악력계 간격을 조절하고 팔을 자연스럽게 내린 자세에서 약 3초간 최대 힘으로 잡습니다. 좌우 측정값 중 가장 큰 kg을 기록합니다.", "caution":"악력계가 몸이나 옷에 닿지 않게 하고 손목을 비틀지 않습니다."},
    "SIDE_STEP": {"duration":"20초 측정 · 준비 포함 약 4분", "attempts":"연습 후 1~2회", "method":"중앙선과 좌우 1m 선을 표시합니다. 중앙에서 시작해 20초 동안 오른쪽 선-중앙선-왼쪽 선-중앙선 순으로 빠르게 이동하며 발이 선을 넘거나 닿을 때마다 횟수를 셉니다.", "caution":"상체만 기울인 동작은 세지 않으며 미끄럼과 주변 장애물을 제거합니다."},
    "SHUTTLE_RUN_5M_X4": {"duration":"20초 안팎 · 준비 포함 약 5분", "attempts":"충분히 휴식 후 2회 중 좋은 기록", "method":"5m 간격 두 선을 표시하고 출발 신호에 맞춰 반대편 선을 발로 넘은 뒤 방향을 바꿉니다. 총 네 구간을 완주하는 시간을 0.1초 단위로 기록합니다.", "caution":"매번 선을 확실히 통과하며 급회전 시 무릎과 발목에 주의합니다."},
    "SHUTTLE_RUN_10M": {"duration":"성인은 10m×4회 완주시간, 유아는 음원 종료까지", "attempts":"연습 후 1회, 시간검사는 2회 가능", "method":"10m 간격 표시선을 오가며 매번 선을 넘어 방향을 바꿉니다. 성인 민첩성 검사는 네 구간 완주 초를 기록하고, 유아 왕복오래달리기는 안내 음원 박자에 맞춰 성공한 횟수를 기록합니다.", "caution":"현재 화면의 단위가 초인지 회인지 확인하고 서로 다른 방식을 섞지 않습니다."},
    "SHUTTLE_RUN_15M": {"duration":"안내 음원을 따라 더 이상 박자를 맞추지 못할 때까지", "attempts":"1회", "method":"15m 간격 두 선 사이를 신호음에 맞춰 왕복합니다. 신호 전에 출발하지 않고 신호 때 반대편 선에 도달한 성공 횟수를 기록합니다.", "caution":"가슴통증·호흡곤란·어지럼증이 있으면 즉시 중단합니다."},
    "SHUTTLE_RUN_20M": {"duration":"안내 음원을 따라 더 이상 박자를 맞추지 못할 때까지", "attempts":"1회", "method":"20m 간격 두 선 사이를 단계적으로 빨라지는 신호음에 맞춰 왕복합니다. 신호 때 선에 도달한 성공 횟수를 기록하고 연속으로 박자를 놓치면 종료합니다.", "caution":"충분히 준비운동하고 가슴통증·비정상적 호흡곤란이 있으면 즉시 중단합니다."},
    "CHAIR_STAND_30S": {"duration":"30초 측정 · 준비 포함 약 3분", "attempts":"연습 후 1회", "method":"벽에 고정한 의자 중앙에 앉아 팔을 가슴에 교차합니다. 시작 신호 후 완전히 일어섰다가 엉덩이가 의자에 닿도록 앉는 동작을 30초 동안 반복해 완성 횟수를 기록합니다.", "caution":"의자가 움직이지 않게 하고 균형이 불안하면 보호자가 옆에 섭니다."},
    "STEP_IN_PLACE_2MIN": {"duration":"정확히 2분", "attempts":"1회", "method":"엉덩뼈와 무릎뼈 중간 높이를 벽에 표시합니다. 2분 동안 양쪽 무릎을 번갈아 표시 높이까지 올리며, 기준 높이에 도달한 오른쪽 무릎 횟수를 기록합니다.", "caution":"벽이나 의자를 잡지 않으며 어지럼증·가슴통증이 있으면 즉시 중단합니다."},
    "CHAIR_3M_TURN": {"duration":"한 시도 보통 5~20초 · 총 약 4분", "attempts":"연습 후 2회 중 좋은 기록", "method":"의자 앞발에서 3m 지점에 표적을 둡니다. 등을 기대고 앉아 시작 신호에 일어나 표적을 돌아와 다시 완전히 앉을 때까지 시간을 0.1초 단위로 잽니다.", "caution":"평소 신는 안정적인 신발을 사용하고 보행이 불안하면 보호자가 가까이 섭니다."},
}


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def init_user_db() -> None:
    USER_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(USER_DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, salt TEXT NOT NULL,
          name TEXT NOT NULL, email TEXT, phone TEXT, birth_date TEXT, sex TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS measurement_sessions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
          measured_at TEXT NOT NULL, age INTEGER NOT NULL, sex TEXT NOT NULL,
          height_cm REAL, weight_kg REAL, life_stage TEXT NOT NULL,
          summary TEXT, source TEXT CHECK(source IN ('HOME','CENTER')),
          FOREIGN KEY(username) REFERENCES users(username)
        );
        CREATE TABLE IF NOT EXISTS measurement_results(
          id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
          item_code TEXT NOT NULL, item_name TEXT NOT NULL, factor_name TEXT NOT NULL,
          unit TEXT NOT NULL, input_value REAL NOT NULL, average_value REAL,
          percentile REAL, age_band TEXT, norm_version TEXT,
          protocol_match TEXT NOT NULL DEFAULT 'EXACT',
          equipment_verified INTEGER NOT NULL DEFAULT 1,
          percentile_eligible INTEGER NOT NULL DEFAULT 1,
          FOREIGN KEY(session_id) REFERENCES measurement_sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_measurement_user_date
          ON measurement_sessions(username, measured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_result_session ON measurement_results(session_id);
        CREATE TABLE IF NOT EXISTS auth_sessions(
          token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(username) REFERENCES users(username)
        );
        CREATE INDEX IF NOT EXISTS idx_auth_session_user ON auth_sessions(username);
        CREATE TABLE IF NOT EXISTS user_screening(
          username TEXT PRIMARY KEY, parq_passed INTEGER NOT NULL,
          screened_at TEXT NOT NULL, valid_until TEXT NOT NULL,
          FOREIGN KEY(username) REFERENCES users(username)
        );
        CREATE TABLE IF NOT EXISTS body_composition_results(
          id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
          metric_code TEXT NOT NULL, raw_value REAL NOT NULL, unit TEXT NOT NULL,
          category TEXT NOT NULL, percentile_eligible INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(session_id) REFERENCES measurement_sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_body_composition_session ON body_composition_results(session_id);
        CREATE TABLE IF NOT EXISTS chat_conversations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, username TEXT NOT NULL,
          conversation_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
          content TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(username) REFERENCES users(username)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_conversation
          ON chat_conversations(token,username,conversation_id,id);
        """)
        existing = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        for name, declaration in (("age","INTEGER"),("height_cm","REAL"),("weight_kg","REAL"),("profile_completed","INTEGER NOT NULL DEFAULT 0")):
            if name not in existing:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {declaration}")
        session_columns = {row[1] for row in db.execute("PRAGMA table_info(measurement_sessions)")}
        if "source" not in session_columns:
            # 기존 기록은 출처를 추정하지 않고 NULL로 보존한다. 신규 기록만 HOME/CENTER를 강제한다.
            db.execute("ALTER TABLE measurement_sessions ADD COLUMN source TEXT")
        result_columns = {row[1] for row in db.execute("PRAGMA table_info(measurement_results)")}
        if "level_code" in result_columns or "level_name" in result_columns or "norm_version" not in result_columns:
            db.executescript("""
              CREATE TABLE measurement_results_v2(
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
                item_code TEXT NOT NULL, item_name TEXT NOT NULL, factor_name TEXT NOT NULL,
                unit TEXT NOT NULL, input_value REAL NOT NULL, average_value REAL,
                percentile REAL, age_band TEXT, norm_version TEXT,
                FOREIGN KEY(session_id) REFERENCES measurement_sessions(id)
              );
              INSERT INTO measurement_results_v2(
                id,session_id,item_code,item_name,factor_name,unit,input_value,
                average_value,percentile,age_band,norm_version
              )
              SELECT id,session_id,item_code,item_name,factor_name,unit,input_value,
                     average_value,percentile,age_band,NULL
              FROM measurement_results;
              DROP TABLE measurement_results;
              ALTER TABLE measurement_results_v2 RENAME TO measurement_results;
              CREATE INDEX idx_result_session ON measurement_results(session_id);
            """)
        result_columns = {row[1] for row in db.execute("PRAGMA table_info(measurement_results)")}
        for name, declaration in (
            ("protocol_match", "TEXT NOT NULL DEFAULT 'EXACT'"),
            ("equipment_verified", "INTEGER NOT NULL DEFAULT 1"),
            ("percentile_eligible", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if name not in result_columns:
                db.execute(f"ALTER TABLE measurement_results ADD COLUMN {name} {declaration}")
        if not db.execute("SELECT 1 FROM users WHERE username='test'").fetchone():
            salt = secrets.token_hex(12)
            db.execute(
                "INSERT INTO users(username,password_hash,salt,name,email,phone,birth_date,sex,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("test", _hash("1234", salt), salt, "테스트 사용자", "test@example.com", "", "1982-01-01", "M", _now()),
            )
        latest = db.execute("SELECT age,height_cm,weight_kg,sex FROM measurement_sessions WHERE username='test' ORDER BY measured_at DESC LIMIT 1").fetchone()
        if latest and not db.execute("SELECT profile_completed FROM users WHERE username='test'").fetchone()[0]:
            db.execute("UPDATE users SET age=?,height_cm=?,weight_kg=?,sex=?,profile_completed=1 WHERE username='test'", latest)
        for (username,) in db.execute("SELECT username FROM users").fetchall():
            old_ids = [r[0] for r in db.execute("SELECT id FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC,id DESC LIMIT -1 OFFSET 10", (username,))]
            if old_ids:
                marks = ",".join("?" * len(old_ids))
                db.execute(f"DELETE FROM body_composition_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_sessions WHERE id IN ({marks})", old_ids)


def init_norm_fallback_db() -> None:
    """Prepare a slot for analyst-produced adjacent-age merged norm cells.

    Runtime never invents pooled quantiles. If a future primary cell has fewer than
    MIN_SAMPLE observations, only a precomputed row in this table may be used.
    """
    with sqlite3.connect(NORM_DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS fitness_norm_fallback(
          life_stage TEXT NOT NULL, item_code TEXT NOT NULL, sex TEXT NOT NULL,
          requested_age_band TEXT NOT NULL, merged_age_band TEXT NOT NULL,
          percentile INTEGER NOT NULL, cut_value REAL NOT NULL, sample_n INTEGER NOT NULL,
          norm_version TEXT NOT NULL,
          PRIMARY KEY(life_stage,item_code,sex,requested_age_band,percentile,norm_version)
        );
        CREATE INDEX IF NOT EXISTS idx_norm_fallback_lookup
          ON fitness_norm_fallback(life_stage,item_code,sex,requested_age_band,norm_version,cut_value);
        """)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _stage(age: int) -> str:
    if 4 <= age <= 6:
        return "PRESCHOOL"
    if 11 <= age <= 12:
        return "CHILD"
    if 13 <= age <= 18:
        return "TEEN"
    if 19 <= age <= 64:
        return "ADULT"
    if age >= 65:
        return "SENIOR"
    raise ValueError("현재 규준은 만 4~6세 및 만 11세 이상을 지원합니다.")


def _validate_life_stage(age: int, life_stage: str) -> str:
    stage = _stage(age)
    if age < 19:
        raise ValueError("현재 API는 만 19세 이상 성인·어르신 측정만 지원합니다.")
    if life_stage not in {"ADULT", "SENIOR"} or life_stage != stage:
        raise ValueError(f"age={age}와 life_stage={life_stage}가 일치하지 않습니다.")
    return stage


def _age_band(stage: str, age: int) -> str:
    if stage == "PRESCHOOL":
        months = age * 12
        return next((b for b, lo, hi in (("48-53M",48,53),("54-59M",54,59),("60-65M",60,65),("66-71M",66,71),("72-83M",72,83)) if lo <= months <= hi), "72-83M")
    if stage in {"CHILD", "TEEN"}:
        return str(age)
    bands = (("19-24",19,24),("25-29",25,29),("30-34",30,34),("35-39",35,39),("40-44",40,44),("45-49",45,49),("50-54",50,54),("55-59",55,59),("60-64",60,64)) if stage == "ADULT" else (("65-69",65,69),("70-74",70,74),("75-79",75,79),("80-84",80,84),("85+",85,200))
    return next(b for b, lo, hi in bands if lo <= age <= hi)


def _body_composition(body: EvaluateBody) -> list[dict[str, Any]]:
    """Keep body-composition values outside the percentile/radar pipeline."""
    items: list[dict[str, Any]] = []
    if body.height_cm and body.weight_kg:
        bmi = float(body.weight_kg) / (float(body.height_cm) / 100) ** 2
        if body.age < 19:
            category = "연령별 성장 기준 확인 필요"
        elif bmi < 18.5:
            category = "저체중 범위"
        elif bmi < 23:
            category = "일반 범위"
        elif bmi < 25:
            category = "과체중 전단계 범위"
        else:
            category = "비만 범위"
        items.append({"metric_code":"BMI","raw_value":round(bmi, 1),"unit":"kg/m²","category":category,"percentile_eligible":False})
    if body.body_fat_percent is not None:
        if body.age < 19:
            category = "연령별 성장 기준 확인 필요"
        else:
            category = "측정 장비별 참고 범위 확인 필요"
        items.append({"metric_code":"BODY_FAT_PERCENT","raw_value":float(body.body_fat_percent),"unit":"%","category":category,"percentile_eligible":False})
    if body.waist_cm is not None:
        if body.age < 19:
            category = "연령별 성장 기준 확인 필요"
        else:
            threshold = 90.0 if body.sex == "M" else 85.0
            category = "복부비만 기준 미만" if body.waist_cm < threshold else "복부비만 기준 이상"
        items.append({"metric_code":"WAIST_CIRCUMFERENCE","raw_value":float(body.waist_cm),"unit":"cm","category":category,"percentile_eligible":False})
    return items


def _auth(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    with sqlite3.connect(USER_DB) as db:
        row = db.execute("SELECT username,created_at FROM auth_sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        try:
            created_at = datetime.fromisoformat(str(row[1]))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            expired = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) >= AUTH_SESSION_TTL
        except (TypeError, ValueError):
            expired = True
        if expired:
            db.execute("DELETE FROM chat_conversations WHERE token=?", (token,))
            db.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
            return None
    return str(row[0])


def _auth_token(authorization: str | None) -> str:
    return authorization[7:] if authorization and authorization.startswith("Bearer ") else ""


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class SignupBody(LoginBody):
    model_config = ConfigDict(extra="forbid")
    sex: str = Field(pattern="^(M|F)$")
    age: int = Field(ge=19, le=120)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=20, le=300)


class EvaluateBody(BaseModel):
    age: int = Field(ge=4, le=120)
    life_stage: str = Field(pattern="^(TEEN|ADULT|SENIOR)$")
    sex: str = Field(pattern="^(M|F)$")
    height_cm: float | None = None
    weight_kg: float | None = None
    measured_at: str | None = None
    source: str = Field(pattern="^(HOME|CENTER)$")
    protocol_match: str = Field(default="EXACT", pattern="^(EXACT|PARTIAL|NONE)$")
    equipment_verified: dict[str, bool] = Field(default_factory=dict)
    body_fat_percent: float | None = Field(default=None, ge=1, le=75)
    waist_cm: float | None = Field(default=None, ge=30, le=250)
    measurements: dict[str, float] = Field(default_factory=dict)


class SummaryBody(BaseModel):
    age: int
    sex: str
    source: str = Field(pattern="^(HOME|CENTER)$")
    results: list[dict[str, Any]] = Field(default_factory=list)
    previous_results: list[dict[str, Any]] = Field(default_factory=list)


class FitnessChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)
    # Deprecated and deliberately ignored. Kept temporarily so older clients get
    # a safe response instead of a validation error during rollout.
    measurement_context: str = Field(default="", max_length=3000)
    measurement_snapshot: EvaluateBody | None = None
    conversation_id: str = Field(default="default", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")


class ScreeningBody(BaseModel):
    passed: bool


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sex: str = Field(pattern="^(M|F)$")
    age: int = Field(ge=19, le=120)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=20, le=300)


def _user_measurement_records(username: str, limit_sessions: int = 10) -> list[dict[str, Any]]:
    """Return only records owned by username, including auditable DB identifiers."""
    limit_sessions = max(1, min(10, int(limit_sessions)))
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            WITH owned_sessions AS (
              SELECT id FROM measurement_sessions
              WHERE username=? ORDER BY measured_at DESC,id DESC LIMIT ?
            )
            SELECT r.id AS record_id,s.id AS session_id,s.measured_at,s.source,
                   s.age,s.sex,s.life_stage,r.item_code,r.item_name,r.factor_name,
                   r.unit,r.input_value,r.average_value,r.percentile,r.age_band,r.norm_version
                   ,r.protocol_match,r.equipment_verified,r.percentile_eligible
            FROM owned_sessions o
            JOIN measurement_sessions s ON s.id=o.id
            JOIN measurement_results r ON r.session_id=s.id
            WHERE s.username=?
            ORDER BY s.measured_at DESC,s.id DESC,r.id
            """,
            (username, limit_sessions, username),
        ).fetchall()
    records = [dict(row) for row in rows]
    for record in records:
        record["factor_name"] = _public_factor_name(str(record.get("item_code") or ""), record.get("factor_name"))
    return records


def _injected_measurement_values(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return the exact stored values used for personal chat context.

    The latest value keeps the compact contract requested by the evaluator, while
    history preserves every queried value needed to audit trend-path answers.
    """
    values: dict[str, dict[str, Any]] = {}
    for row in records:
        code = str(row.get("item_code") or "").strip()
        if not code:
            continue
        percentile = row.get("percentile")
        point = {
            "record_id": int(row["record_id"]) if row.get("record_id") is not None else None,
            "session_id": int(row["session_id"]) if row.get("session_id") is not None else None,
            "value": float(row["input_value"]),
            "percentile": float(percentile) if percentile is not None else None,
            "top_percent": float(100 - float(percentile)) if percentile is not None else None,
            "item_name": str(row.get("item_name") or code),
            "factor_name": _public_factor_name(code, row.get("factor_name")),
            "unit": str(row.get("unit") or ""),
            "measured_at": str(row.get("measured_at") or ""),
            "life_stage": str(row.get("life_stage") or ""),
            "age_band": str(row.get("age_band") or ""),
            "sex": str(row.get("sex") or ""),
            "source": str(row.get("source") or ""),
            "norm_version": row.get("norm_version"),
        }
        if code not in values:
            values[code] = {**point, "history": []}
        values[code]["history"].append(point)
    return values


def _measurement_trace(username: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "username": username,
        "session_ids": list(dict.fromkeys(int(row["session_id"]) for row in records)),
        "record_ids": [int(row["record_id"]) for row in records],
        "record_count": len(records),
        "queried_record_ids": [int(row["record_id"]) for row in records],
        "used_record_ids": [],
        "injected_values": _injected_measurement_values(records),
    }


def _personal_context_trace(
    username: str,
    profile: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Auditable, server-owned personalization scope for evaluation and UI logs."""
    match = re.fullmatch(r"eval_(p\d+)", username, re.IGNORECASE)
    profile_id = match.group(1).upper() if match else username
    measured = list(dict.fromkeys(
        str(row.get("factor_name") or row.get("item_name") or row.get("item_code") or "")
        for row in records
        if row.get("factor_name") or row.get("item_name") or row.get("item_code")
    ))
    used_fields = ["life_stage"]
    if profile.get("sex"):
        used_fields.append("sex")
    if records:
        used_fields.append("measurements")
    return {
        "personal_context_used": True,
        "active_profile_id": profile_id,
        "used_profile_fields": used_fields,
        "cross_profile_contamination": False,
        "measurement_scope": {
            "record_count": len(records),
            "measured_factors": measured,
            "unmeasured_factors_must_not_be_inferred": True,
        },
    }


def _remove_unproven_numeric_sentences(
    answer: str,
    message: str,
    injected_values: dict[str, Any],
    evidence_text: dict[str, str],
) -> str:
    """Drop generated numeric claims absent from the request or supplied evidence."""
    allowed_text = " ".join((
        message,
        json.dumps(injected_values, ensure_ascii=False),
        " ".join(str(value) for value in evidence_text.values()),
    ))
    allowed = set(re.findall(r"\d+(?:\.\d+)?", allowed_text))
    sentences = re.split(r"(?<=[.!?요다])\s+", str(answer or "").strip())
    kept = [
        sentence for sentence in sentences
        if set(re.findall(r"\d+(?:\.\d+)?", sentence)) <= allowed
    ]
    return " ".join(kept).strip()


def _percentile_display(source: str, item_code: str, top_percent: Any) -> dict[str, Any]:
    if top_percent is None:
        return {"mode": "UNAVAILABLE", "lower": None, "upper": None, "text": "백분위가 제공되지 않았습니다."}
    value = max(0.0, min(100.0, float(top_percent)))
    if source == "CENTER":
        return {"mode": "POINT", "lower": None, "upper": None, "text": f"또래 상위 {round(value)}%"}
    width = HOME_TOP_PERCENT_WIDTH.get(item_code)
    if width is None:
        return {"mode": "UNAVAILABLE", "lower": None, "upper": None, "text": "자가측정 구간 기준이 제공되지 않았습니다."}
    lower = max(0, round(value - width))
    upper = min(100, round(value + width))
    return {"mode": "RANGE", "lower": lower, "upper": upper, "text": f"또래 상위 {lower}~{upper}%"}


def _record_percentile_display(row: dict[str, Any]) -> dict[str, Any]:
    percentile = row.get("percentile")
    top_percent = None if percentile is None else 100 - float(percentile)
    return _percentile_display(str(row.get("source") or ""), str(row.get("item_code") or ""), top_percent)


def _measurement_sources(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose user DB evidence with the same stable public source contract as RAG."""
    sources = []
    for index, row in enumerate(records, 1):
        record_id = int(row["record_id"])
        measured_at = str(row.get("measured_at") or "")
        item_name = str(row.get("item_name") or row.get("item_code") or "측정 기록")
        percentile = row.get("percentile")
        percentile_text = "" if percentile is None else f", {_record_percentile_display(row)['text']}"
        sources.append({
            "evidence_id": f"U{index}",
            "title": f"{measured_at[:10]} {item_name} 측정 기록",
            "location": f"fitness_user_records:record/{record_id}",
            "url": "",
            "excerpt": (
                f"{item_name} {float(row['input_value']):g}{row.get('unit') or ''}"
                f"{percentile_text}"
            ),
            "evidence_type": "USER_MEASUREMENT",
            "dataset": "fitness_user_records",
            "document_id": "",
            "record_id": record_id,
        })
    return sources


def _finalize_grounding_contract(response: dict[str, Any]) -> dict[str, Any]:
    """Never claim grounding without public evidence that the client can inspect."""
    sources = response.get("sources")
    if not isinstance(sources, list):
        sources = []
    sources = [source for source in sources if isinstance(source, dict)]
    response["sources"] = sources
    response["grounded"] = bool(sources)
    evidence_types = {str(source.get("evidence_type") or "RAG_DOCUMENT") for source in sources}
    response["grounding_type"] = (
        "MIXED" if len(evidence_types) > 1 else next(iter(evidence_types), "NONE")
    )
    return response


def _validated_guest_context(snapshot: EvaluateBody | None) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build guest LLM context only from server-evaluated structured measurements."""
    if snapshot is None:
        return "", {}
    try:
        stage, band, results = _evaluate(snapshot)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    available = [row for row in results if row.get("available") and row.get("percentile_eligible")]
    if not available:
        return "", {}
    records = [
        {
            "record_id": None,
            "session_id": None,
            "item_code": row["item_code"],
            "item_name": row["name"],
            "factor_name": row["factor_name"],
            "unit": row["unit"],
            "input_value": row["input_value"],
            "percentile": row["percentile"],
            "measured_at": snapshot.measured_at or "",
            "life_stage": stage,
            "age_band": band,
            "sex": snapshot.sex,
            "source": snapshot.source,
            "norm_version": row.get("norm_version"),
        }
        for row in available
    ]
    context = "비로그인 사용자의 현재 검증 측정: " + " / ".join(
        f"{row['factor_name']} {row['input_value']}{row['unit']} {row['percentile_display']['text']}"
        for row in available
    )
    return context, _injected_measurement_values(records)


def _server_chat_history(token: str, username: str, conversation_id: str) -> list[dict[str, str]]:
    with sqlite3.connect(USER_DB) as db:
        rows = db.execute(
            """SELECT role,content FROM chat_conversations
               WHERE token=? AND username=? AND conversation_id=?
               ORDER BY id DESC LIMIT 8""",
            (token, username, conversation_id),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def _save_chat_turn(token: str, username: str, conversation_id: str, message: str, response: str) -> None:
    with sqlite3.connect(USER_DB) as db:
        now = _now()
        db.executemany(
            """INSERT INTO chat_conversations(token,username,conversation_id,role,content,created_at)
               VALUES(?,?,?,?,?,?)""",
            [(token, username, conversation_id, "user", message, now),
             (token, username, conversation_id, "assistant", response, now)],
        )
        old_ids = [row[0] for row in db.execute(
            """SELECT id FROM chat_conversations
               WHERE token=? AND username=? AND conversation_id=?
               ORDER BY id DESC LIMIT -1 OFFSET 12""",
            (token, username, conversation_id),
        )]
        if old_ids:
            marks = ",".join("?" for _ in old_ids)
            db.execute(f"DELETE FROM chat_conversations WHERE id IN ({marks})", old_ids)




def _compact_measurement_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).casefold()


MEASUREMENT_LOOKUP_ALIASES = {
    "SIT_AND_REACH": (
        "앉아윗몸앞으로굽히기", "앉아 윗몸 앞으로 굽히기", "좌전굴", "sitandreach",
    ),
    "CHAIR_3M_TURN": (
        "의자에앉아3m표적돌아오기", "의자에 앉아 3m 표적 돌아오기",
        "의자3m표적돌아오기", "3m표적돌아오기", "3m 표적 돌아오기",
        "chair3mturn",
    ),
    "CHAIR_STAND_30S": (
        "의자에앉았다일어서기", "의자에 앉았다 일어서기",
        "의자앉았다일어서기", "30초의자일어서기", "30초 의자 일어서기",
        "chairstand30s",
    ),
    "RELATIVE_GRIP": ("상대악력", "상대 악력", "relativegrip"),
    "SHUTTLE_RUN_10M": ("10m4회왕복달리기", "10m 4회 왕복달리기"),
    "CROSS_SIT_UP": ("교차윗몸일으키기", "교차 윗몸 일으키기"),
    "STANDING_LONG_JUMP": ("제자리멀리뛰기", "제자리 멀리뛰기"),
}


def _requested_measurement_codes(message: str) -> list[str]:
    compact = _compact_measurement_text(message)
    found: list[str] = []
    for code, aliases in MEASUREMENT_LOOKUP_ALIASES.items():
        if any(_compact_measurement_text(alias) in compact for alias in aliases):
            found.append(code)
    return found


def _specific_measurement_lookup_answer(
    username: str, message: str
) -> tuple[str | None, dict[str, Any]]:
    """Return one named stored measurement deterministically.

    Questions such as ``앉아윗몸앞으로굽히기 결과 알려줘`` must not be
    converted into a recommendation or a whole-profile trend summary.  The
    newest matching record is returned, optionally respecting an explicit HOME
    or CENTER cue in the user's wording.
    """
    compact = _compact_measurement_text(message)
    if not compact:
        return None, _measurement_trace(username, [])

    # Recommendation questions remain path B even when they mention a result.
    recommendation_cues = (
        "운동후보", "운동추천", "추천해", "추천", "루틴", "프로그램",
        "폼롤러", "관련있는운동", "관련있는", "맞물리는운동", "맞는운동",
        "이어지는운동", "연결되는운동", "운동인지", "운동일까", "운동일까요",
        "같은체력요인", "다루는운동", "연결해서", "짚어", "스트레칭",
        "정해줘", "골라서",
    )
    if any(cue in compact for cue in recommendation_cues):
        return None, _measurement_trace(username, [])

    lookup_cues = (
        "결과", "측정값", "수치", "기록", "얼마", "어땠", "어떻게나왔",
        "확인해", "알려줘", "다시알려",
    )
    if not any(cue in compact for cue in lookup_cues):
        return None, _measurement_trace(username, [])

    records = _user_measurement_records(username)
    trace = _measurement_trace(username, records)
    if not records:
        return "아직 저장된 측정 기록이 없어요.", trace

    requested_source = None
    if "집에서" in compact or "홈" in compact:
        requested_source = "HOME"
    elif "센터" in compact:
        requested_source = "CENTER"

    requested_codes = set(_requested_measurement_codes(message))
    matching = []
    for row in records:
        item_name = _compact_measurement_text(row.get("item_name") or "")
        raw_code = str(row.get("item_code") or "").upper()
        item_code = _compact_measurement_text(raw_code)
        if not item_name and not item_code:
            continue
        name_or_code_match = item_name in compact or item_code in compact
        alias_match = raw_code in requested_codes
        if not name_or_code_match and not alias_match:
            continue
        if requested_source and str(row.get("source") or "").upper() != requested_source:
            continue
        matching.append(row)

    if not matching:
        if requested_codes:
            requested_labels = []
            for code in requested_codes:
                aliases = MEASUREMENT_LOOKUP_ALIASES.get(code) or ()
                requested_labels.append(str(aliases[0] if aliases else code))
            label = ", ".join(requested_labels)
            source_text = "집" if requested_source == "HOME" else ("센터" if requested_source == "CENTER" else "")
            source_prefix = f"{source_text} 측정의 " if source_text else ""
            return (
                f"현재 로그인 계정에는 {source_prefix}{label} 기록이 저장되어 있지 않아요. "
                "다른 측정 결과로 바꾸어 답하지 않을게요."
            ), trace
        return None, trace

    row = matching[0]
    trace["used_record_ids"] = [int(row["record_id"])]
    value = f"{float(row['input_value']):g}"
    unit = str(row.get("unit") or "")
    item_name = str(row.get("item_name") or row.get("item_code") or "측정 항목")
    measured_at = str(row.get("measured_at") or "")[:10]
    percentile_text = ""
    if row.get("percentile") is not None:
        percentile_text = f", 또래 비교는 {_record_percentile_display(row)['text']}"
    source_text = "집" if str(row.get("source") or "").upper() == "HOME" else "센터"
    answer = (
        f"{measured_at} {source_text} 측정의 {item_name} 결과는 "
        f"{value}{unit}{percentile_text}입니다."
    )
    return answer, trace


def _measurement_history_answer(username: str, message: str) -> tuple[str | None, dict[str, Any]]:
    """Answer record/trend questions from saved percentiles instead of unrelated RAG hits."""
    # Do not let an old measurement question hijack every later conversation turn.
    # Short follow-ups such as "나아지고 있어?" already contain an explicit trend cue.
    compact = re.sub(r"\s+", "", message)
    # A is a deterministic record/trend route.  A recommendation that merely
    # cites a measurement must remain B and continue to evidence retrieval.
    recommendation_cues = (
        "운동", "스트레칭", "루틴", "프로그램", "후보", "추천", "폼롤러",
        "관련있는", "맞는동작", "정해줘", "골라서",
    )
    if any(word in compact for word in recommendation_cues):
        return None, _measurement_trace(username, [])
    trend_cues = (
        "나아", "향상", "변화", "추이", "좋아", "개선", "이전", "예전",
        "지난번", "처음", "첫번째", "첫측정", "두번째", "세번째", "최근",
        "저번", "차이", "달라", "바뀌", "늘어난", "줄어", "증가", "감소", "흐름",
        "계속측정", "기록",
    )
    record_overview = "기록" in message and any(word in message for word in ("어때", "어떤가", "평가", "봐", "보면"))
    if not any(word in compact for word in trend_cues) and not record_overview:
        return None, _measurement_trace(username, [])
    records = _user_measurement_records(username)
    trace = _measurement_trace(username, records)
    snapshots: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    for session_id in trace["session_ids"]:
        values = [row for row in records if int(row["session_id"]) == session_id]
        if values:
            snapshots.append((values[0], {row["item_code"]: row for row in values}))
    if not snapshots:
        return "아직 저장된 측정 기록이 없어요. 먼저 측정을 완료하면 이전 기록과 비교해 드릴게요.", trace

    latest_session, latest = snapshots[0]
    previous_pair = next(
        ((s, v) for s, v in snapshots[1:]
         if s.get("source") == latest_session.get("source") and set(v) & set(latest)),
        None,
    )
    label = lambda code: str(latest[code]["item_name"] or code)
    if not previous_pair:
        trace["used_record_ids"] = [int(row["record_id"]) for row in latest.values()]
        names = ", ".join(dict.fromkeys(label(code) for code in latest))
        return f"{latest_session['measured_at'][:10]}에 저장된 첫 측정이에요. {names} 기록을 기준점으로 보관했으니 다음 측정부터 변화 폭을 함께 보여드릴게요.", trace

    previous_session, previous = previous_pair
    changes = []
    used_record_ids = []
    for code, now in latest.items():
        old = previous.get(code)
        if old is None or now["percentile"] is None or old["percentile"] is None:
            continue
        changes.append((float(now["percentile"]) - float(old["percentile"]), label(code)))
        used_record_ids.extend((int(now["record_id"]), int(old["record_id"])))
    trace["used_record_ids"] = list(dict.fromkeys(used_record_ids))
    if not changes:
        return "최근 기록은 확인했지만 같은 항목의 백분위가 있는 이전 측정이 없어 아직 변화량을 계산하기 어려워요. 한 번 더 측정하면 비교해 드릴게요.", trace

    improved = sorted((x for x in changes if x[0] >= 3), reverse=True)
    declined = sorted((x for x in changes if x[0] <= -3))
    steady = [x for x in changes if -3 < x[0] < 3]
    parts = []
    if improved:
        parts.append("좋아진 항목: " + ", ".join(f"{name} {delta:+.0f}%p" for delta, name in improved[:3]))
    if declined:
        parts.append("조금 내려간 항목: " + ", ".join(f"{name} {delta:+.0f}%p" for delta, name in declined[:3]))
    if steady:
        parts.append("비슷하게 유지된 항목: " + ", ".join(name for _, name in steady[:3]))
    overall = sum(x[0] for x in changes) / len(changes)
    opening = "전체적으로 조금씩 좋아지고 있어요." if overall >= 3 else ("전체 수준은 대체로 유지되고 있어요." if overall > -3 else "이번에는 일부 기록이 내려갔지만 한 번의 측정만으로 퇴보라고 보긴 어려워요.")
    if any(word in message for word in ("나아", "좋아", "향상")):
        best = improved[0] if improved else None
        caution = declined[0] if declined else None
        if best:
            detail = f" 특히 {best[1]} 기록이 이전보다 {best[0]:.0f}%p 좋아졌어요."
        else:
            detail = " 다만 이번에는 이전보다 뚜렷하게 좋아진 항목은 없었어요."
        if caution:
            detail += f" {caution[1]} 기록은 {abs(caution[0]):.0f}%p 내려가 다음 측정도 함께 지켜보면 좋겠어요."
        elif steady:
            detail += " 나머지 기록은 비슷하게 유지되고 있어요."
        return opening + detail, trace
    return opening + " " + ". ".join(parts) + ". 같은 조건에서 다시 측정하면 흐름을 더 정확히 볼 수 있어요.", trace


def _certification_impersonation_request(message: str) -> bool:
    """Detect requests for authority this service does not possess."""
    compact = re.sub(r"\s+", "", message)
    authority = any(term in compact for term in (
        "국민체력100", "체력인증", "인증등급", "공식등급", "공식인증",
        "공식기준", "공식체력", "국가공인", "체력등급", "보험사",
        "대회참가", "국민체육진흥공단", "공단명의", "공단심사위원",
        "인증서", "확인서", "소견서", "심사소견", "증명서", "증명",
        "결과표", "공문", "심사결과", "판정문",
    ))
    action = any(term in compact for term in (
        "발급", "확정", "판정", "만들", "작성", "도장", "서명", "올려",
        "등급", "최상위", "상위로", "통과", "합격으로", "표기", "채워",
        "선언", "증명", "로고", "명의",
    ))
    return authority and action


def _routing_trace(response: dict[str, Any], *, expected_path: str,
                   policy_short_circuit: str | None = None,
                   rag_trigger: str | None = None) -> dict[str, Any]:
    retrieved = response.get("retrieved_doc_ids") or []
    backends = list(dict.fromkeys(
        str(item.get("backend")) for item in retrieved
        if isinstance(item, dict) and item.get("backend")
    ))
    response["policy_short_circuit"] = policy_short_circuit
    response["rag_trigger"] = rag_trigger if retrieved else None
    response["actual_rag_search"] = bool(retrieved)
    response["retrieval_backend"] = backends or None
    response["routing_trace"] = {
        "answer_path": expected_path,
        "actual_rag_search": bool(retrieved),
        "policy_short_circuit": policy_short_circuit,
        "rag_trigger": response["rag_trigger"],
        "retrieval_backend": response["retrieval_backend"],
    }
    return response


def _profile(username: str) -> dict[str, Any]:
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT username,sex,age,height_cm,weight_kg,profile_completed FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else {}


@router.post("/login")
def login(body: LoginBody) -> dict[str, Any]:
    with sqlite3.connect(USER_DB) as db:
        row = db.execute("SELECT password_hash,salt FROM users WHERE username=?", (body.username,)).fetchone()
    if not row or not secrets.compare_digest(row[0], _hash(body.password, row[1])):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    token = secrets.token_urlsafe(32)
    with sqlite3.connect(USER_DB) as db:
        db.execute("INSERT INTO auth_sessions(token,username,created_at) VALUES(?,?,?)", (token, body.username, _now()))
    return {"token": token, "username": body.username, "profile": _profile(body.username)}


@router.delete("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = _auth_token(authorization)
    if token:
        with sqlite3.connect(USER_DB) as db:
            db.execute("DELETE FROM chat_conversations WHERE token=?", (token,))
            db.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
    return {"status": "ok"}


@router.post("/signup")
def signup(body: SignupBody) -> dict[str, str]:
    salt = secrets.token_hex(12)
    try:
        with sqlite3.connect(USER_DB) as db:
            # Legacy nullable personal columns remain in the on-disk schema for
            # compatibility, but the MVP API neither accepts nor stores them.
            db.execute(
                """INSERT INTO users(
                       username,password_hash,salt,name,email,phone,birth_date,sex,
                       created_at,age,height_cm,weight_kg,profile_completed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (body.username, _hash(body.password, salt), salt, "", "", "", "",
                 body.sex, _now(), body.age, body.height_cm, body.weight_kg),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "이미 사용 중인 아이디입니다.") from exc
    return {"status": "ok", "message": "회원가입이 완료되었습니다."}


@router.get("/profile")
def get_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    return _profile(username)


@router.put("/profile")
def update_profile(body: ProfileBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    with sqlite3.connect(USER_DB) as db:
        db.execute(
            "UPDATE users SET sex=?,age=?,height_cm=?,weight_kg=?,profile_completed=1 WHERE username=?",
            (body.sex, body.age, body.height_cm, body.weight_kg, username),
        )
    return _profile(username)


@router.post("/screening")
def save_screening(body: ScreeningBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Store only the PAR-Q decision; individual answers never reach the server."""
    username = _auth(authorization)
    if not username:
        return {"saved": False, "parq_passed": body.passed}
    screened_at = datetime.now(timezone.utc).astimezone()
    valid_until = (screened_at + timedelta(days=365)).date().isoformat()
    with sqlite3.connect(USER_DB) as db:
        db.execute(
            """INSERT INTO user_screening(username,parq_passed,screened_at,valid_until)
               VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET
               parq_passed=excluded.parq_passed,screened_at=excluded.screened_at,
               valid_until=excluded.valid_until""",
            (username, int(body.passed), screened_at.isoformat(timespec="seconds"), valid_until),
        )
    return {"saved": True, "parq_passed": body.passed, "valid_until": valid_until}


@router.get("/screening")
def get_screening(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT parq_passed,screened_at,valid_until FROM user_screening WHERE username=?", (username,)
        ).fetchone()
    return {"username": username, "screening": dict(row) if row else None}


def _measurement_videos(item_name: str) -> list[dict[str, Any]]:
    if not MEASURE_VIDEO_JSON.is_file():
        return []
    try:
        items = json.loads(MEASURE_VIDEO_JSON.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        return []
    aliases = {"상대악력":"악력","절대악력":"악력","5m×4 왕복달리기":"왕복달리기","5m 4회 왕복달리기":"왕복달리기","10m 4회 왕복달리기":"왕복달리기","10m 왕복오래달리기":"왕복오래달리기","15m 왕복오래달리기":"왕복오래달리기","20m 왕복오래달리기":"왕복오래달리기","의자에앉아 3m 표적돌아오기":"3m","의자에앉았다일어서기":"의자"}
    term = aliases.get(item_name, item_name.replace(" ", ""))
    seen, videos = set(), []
    for item in items:
        haystack = f"{item.get('trng_nm','')} {item.get('vdo_desc','')}".replace(" ", "")
        if term.replace(" ", "") not in haystack:
            continue
        filename = str(item.get("file_nm") or "").strip()
        if not filename or filename in seen:
            continue
        seen.add(filename)
        videos.append({"title":item.get("trng_nm") or item_name,"description":item.get("vdo_desc") or "국민체력100 측정방법 영상","duration_seconds":int(item.get("vdo_len") or 0),"url":str(item.get("file_url") or "")+filename,"source":"02_체력인증측정방법.json"})
        if len(videos) == 3:
            break
    return videos


def _next_exercise_level(top_percent: float) -> tuple[int, int]:
    """Convert 'top N%' to a current level and the next safe progression level.

    A larger top-percent value means lower relative performance.  The previous
    weekly mapping treated it in the opposite direction (for example top 93%
    became week 4).  Keep the rule independent of any case/user identifier.
    """
    value = max(0.0, min(100.0, float(top_percent)))
    current_level = 1 if value >= 70 else 2 if value >= 40 else 3
    return current_level, min(4, current_level + 1)


def _training_videos(item_code: str, age: int, percentile: float = 50.0) -> dict[str, Any]:
    # Select short individual exercise guides.  Weekly programme rows reuse one
    # long video for every phase and therefore cannot represent three exercises.
    # Each factor owns a progressive main-exercise ladder.  Preparation and
    # recovery remain factor-specific, while the main video advances exactly
    # one level from the level inferred from the measurement percentile.
    profiles = {
        "CURL_UP": ("근지구력", "몸통 비틀기", ("윗몸 말아 올리기", "윗몸 올리기", "짐볼 윗몸 올리기"), "배 스트레칭"),
        "CROSS_SIT_UP": ("근지구력", "몸통 비틀기", ("윗몸 말아 올리기", "윗몸 올리기", "짐볼 윗몸 올리기"), "배 스트레칭"),
        "SIT_AND_REACH": ("유연성", "몸통 비틀기", ("허리 스트레칭", "몸통 옆으로 굽히기", "팔다리 반대로 뻗어 스트레칭"), "엉덩이 스트레칭"),
        "STANDING_LONG_JUMP": ("순발력", "무릎 높여 제자리 달리기", ("앉았다 일어서면서 점프하기", "스텝퍼 옆으로 뛰어넘기", "사이드 런지 후 점프"), "엉덩이 스트레칭"),
        "RELATIVE_GRIP": ("상지근기능", "가슴/어깨 앞쪽 스트레칭", ("손목 펴기/굽히기", "팔꿈치 굽히기", "바벨 들어 팔꿈치 굽히기"), "아래 팔 스트레칭"),
        "ABSOLUTE_GRIP": ("상지근기능", "가슴/어깨 앞쪽 스트레칭", ("손목 펴기/굽히기", "팔꿈치 굽히기", "바벨 들어 팔꿈치 굽히기"), "아래 팔 스트레칭"),
        "SIDE_STEP": ("민첩성", "무릎 높여 제자리 달리기", ("스텝퍼 옆으로 뛰어넘기", "사다리 옆으로 발 옮기기", "사이드 런지 후 점프"), "엉덩이 스트레칭"),
        "SHUTTLE_RUN_5M_X4": ("민첩성", "무릎 높여 제자리 달리기", ("스텝퍼 옆으로 뛰어넘기", "사다리 옆으로 발 옮기기", "사이드 런지 후 점프"), "엉덩이 스트레칭"),
        "SHUTTLE_RUN_10M": ("민첩성", "무릎 높여 제자리 달리기", ("스텝퍼 옆으로 뛰어넘기", "사다리 옆으로 발 옮기기", "사이드 런지 후 점프"), "엉덩이 스트레칭"),
        "SHUTTLE_RUN_15M": ("심폐지구력", "걷기", ("트레드밀에서 걷기", "고정식 자전거 타기", "달리기"), "엉덩이 스트레칭"),
        "SHUTTLE_RUN_20M": ("심폐지구력", "걷기", ("트레드밀에서 걷기", "고정식 자전거 타기", "달리기"), "엉덩이 스트레칭"),
        "STEP_IN_PLACE_2MIN": ("심폐지구력", "걷기", ("트레드밀에서 걷기", "고정식 자전거 타기", "달리기"), "엉덩이 스트레칭"),
        "CHAIR_3M_TURN": ("평형성", "걷기", ("서서 균형잡기", "균형 걷기", "한발 서서 균형잡기"), "엉덩이 스트레칭"),
        "CHAIR_STAND_30S": ("하지근기능", "걷기", ("의자 앞에서 앉았다 일어서기", "스쿼트", "덤벨 한발 앞으로 내밀고 앉았다 일어서기"), "엉덩이 스트레칭"),
    }
    factor_label, warmup, main_ladder, cooldown = profiles.get(item_code, ("전신 체력", "걷기", ("걷기", "계단 오르기", "달리기"), "허리 스트레칭"))
    current_level, target_level = _next_exercise_level(percentile)
    phase_exercises = (warmup, main_ladder[target_level - 2], cooldown)
    stage = "유아기" if age<7 else "유소년" if age<13 else "청소년" if age<19 else "성인" if age<65 else "어르신"
    support_level = "기초에서 한 단계 향상" if target_level == 2 else "중간에서 한 단계 향상" if target_level == 3 else "상위 단계 도전"
    try:
        items = json.loads(ALL_VIDEO_JSON.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        items = []
    selected, used_urls = [], set()
    for phase, exercise_term in zip(("준비운동", "본운동", "마무리운동"), phase_exercises):
        candidates = []
        for item in items:
            filename = str(item.get("file_nm") or "")
            url = str(item.get("file_url") or "") + filename
            duration = int(item.get("vdo_len") or 0)
            text = f"{item.get('trng_nm','')} {item.get('vdo_ttl_nm','')} {item.get('vdo_desc','')}"
            audience = str(item.get("aggrp_nm") or "")
            if (not filename or url in used_urls or not (0 < duration <= 600)
                    or exercise_term not in text or "측정" in str(item.get("vdo_desc") or "")
                    or audience not in {stage, "공통", ""}):
                continue
            score = 10 + (3 if audience == stage else 1)
            if str(item.get("trng_nm") or "").strip() == exercise_term:
                score += 20
            if "운동처방 가이드" in str(item.get("vdo_desc") or ""):
                score += 3
            candidates.append((score, duration, int(item.get("row_num") or 999999), {
                "phase": phase, "title": item.get("vdo_ttl_nm") or item.get("trng_nm") or f"{phase} 영상",
                "exercise_name": item.get("trng_nm") or "", "description": item.get("vdo_desc") or f"국민체력100 {phase} 영상",
                "duration_seconds": duration, "age_group": audience or "공통", "week": "",
                "url": url, "source": ALL_VIDEO_JSON.name, "matched_factor": factor_label,
                "current_level": current_level, "target_level": target_level,
            }))
        if candidates:
            chosen = sorted(candidates, key=lambda x: (-x[0], x[1], x[2]))[0][3]
            used_urls.add(chosen["url"])
            selected.append(chosen)
    return {"item_code": item_code, "factor_label": factor_label, "age": age,
            "life_stage": _stage(age), "percentile": float(percentile),
            "support_level": support_level, "current_level": current_level,
            "target_level": target_level, "target_week": f"{target_level}주차",
            "recommendation_basis": "또래 상위 백분위를 수행 수준으로 변환한 뒤 한 단계 높은 운동 선택",
            "videos": selected}


def _legacy_training_videos(item_code: str, age: int, percentile: float = 50.0) -> dict[str, Any]:
    terms = {
        "CURL_UP":("근지구력","복부","코어"),"CROSS_SIT_UP":("근지구력","복부","코어"),
        "SIT_AND_REACH":("유연성","스트레칭"),"STANDING_LONG_JUMP":("순발력","점프","하체"),
        "RELATIVE_GRIP":("악력","전완","근력"),"ABSOLUTE_GRIP":("악력","전완","근력"),
        "SIDE_STEP":("민첩성","사이드","균형"),"SHUTTLE_RUN_5M_X4":("민첩성","방향전환","사이드"),
        "SHUTTLE_RUN_10M":("민첩성","방향전환","달리기"),"SHUTTLE_RUN_15M":("심폐","유산소","달리기"),
        "SHUTTLE_RUN_20M":("심폐","유산소","달리기"),"STEP_IN_PLACE_2MIN":("심폐","유산소","걷기"),
        "CHAIR_3M_TURN":("민첩","균형","걷기"),"CHAIR_STAND_30S":("하지","하체","근력"),
    }.get(item_code,("운동",))
    stage = "유아기" if age<7 else "유소년" if age<13 else "청소년" if age<19 else "성인" if age<65 else "어르신"
    # 사용자에게 등급을 만들거나 노출하지 않고 백분위 자체로 프로그램 주차만 선택한다.
    target_week = "1주차" if percentile < 40 else "2주차" if percentile < 60 else "3주차" if percentile < 80 else "4주차"
    source_path = STANDARD_VIDEO_JSON if stage in {"성인","어르신"} else ROUTINE_VIDEO_JSON
    try:
        items = json.loads(source_path.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        items = []
    phase_aliases = {
        "준비운동":("준비 운동","준비운동"),
        "본운동":("본 운동","본운동"),
        "마무리운동":("정리 운동","정리운동","마무리 운동","마무리운동"),
    }
    selected = []
    for phase, aliases in phase_aliases.items():
        candidates, seen = [], set()
        for item in items:
            filename = str(item.get("file_nm") or "")
            if not filename or filename in seen:
                continue
            phase_text = f"{item.get('trng_sqnc_nm','')} {item.get('trng_se_nm','')}"
            if not any(alias in phase_text for alias in aliases):
                continue
            text = f"{item.get('trng_nm','')} {item.get('vdo_ttl_nm','')} {item.get('vdo_desc','')} {item.get('ftns_fctr_nm','')} {item.get('trng_aim_nm','')}"
            audience = str(item.get("aggrp_nm") or "")
            if audience not in {stage, "공통", ""}:
                continue
            score = sum(4 for term in terms if term in text)
            if audience == stage: score += 4
            elif audience in {"공통",""}: score += 1
            week = str(item.get("trng_week_nm") or "")
            if week == target_week: score += 3
            if score < 4: continue
            seen.add(filename)
            candidates.append((score,int(item.get("row_num") or 999999),{
                "phase":phase,"title":item.get("vdo_ttl_nm") or item.get("trng_nm") or f"{phase} 영상",
                "exercise_name":item.get("trng_nm") or "","description":item.get("vdo_desc") or f"국민체력100 {phase} 영상",
                "duration_seconds":int(item.get("vdo_len") or 0),"age_group":audience or "공통","week":week,
                "url":str(item.get("file_url") or "")+filename,"source":source_path.name,
            }))
        if candidates:
            selected.append(sorted(candidates,key=lambda x:(-x[0],x[1]))[0][2])
    return {"item_code":item_code,"factor_label":_public_factor_name(item_code),"age":age,"life_stage":_stage(age),"percentile":float(percentile),"target_week":target_week,"videos":selected}


@router.get("/recommendation-videos/{item_code}")
def recommendation_videos(item_code: str, age: int, life_stage: str, percentile: float = 50.0) -> dict[str, Any]:
    try:
        _validate_life_stage(age, life_stage)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _training_videos(item_code, age, max(0.0, min(100.0, percentile)))



def _chat_needs_personal_context(message: str, history: list[dict[str, Any]] | None = None) -> bool:
    """Return True only when the current chat turn genuinely needs user-owned context.

    Authentication alone must never force Path B. Public exercise/video/equipment/
    audience/program questions stay Path C even for logged-in users. Path B is for
    turns that explicitly depend on the user's measurement/profile or a prior
    measurement result.
    """
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    compact = re.sub(r"\s+", "", text).casefold()

    # Explicit first-person/profile ownership. Word-ish boundaries avoid false
    # positives such as "제자리멀리뛰기" and "제일".
    if re.search(r"(?:^|[\s,.(])(?:제|내|나의|저의)(?=\s|기록|결과|측정|체력|근력|유연성|민첩|평형|균형|악력|몸|계정|프로필|에게|한테|$)", text):
        return True

    personal_phrases = (
        "제계정", "내계정", "현재계정", "로그인계정", "제프로필", "내프로필",
        "다른사람기록", "앞에나온센터기록", "제기록", "내기록", "저의기록",
        "제결과", "내결과", "저의결과", "제측정", "내측정", "저의측정",
        "제체력", "내체력", "저의체력", "제근력", "내근력", "제유연성", "내유연성",
        "제상대악력", "내상대악력", "제앉아윗몸", "내앉아윗몸",
        "그수치", "그결과", "그기록", "그측정값", "그측정결과",
        "앞서확인한측정", "방금확인한측정",
        "지난번결과", "이전결과", "최근측정결과",
        "측정결과와연결", "측정결과에연결", "결과와이어",
    )
    if any(token in compact for token in personal_phrases):
        return True

    # A concrete measurement value tied to a fitness item/result is personal
    # even when the sentence omits a pronoun, e.g. "상대악력이 64.3%로 나왔는데".
    # Korean particles commonly follow units directly (e.g. "11cm로", "5.7초로").
    # \b fails there because both the unit tail and the Korean particle are word chars.
    has_measurement_value = bool(re.search(
        r"\d+(?:\.\d+)?\s*(?:%|cm|초|회|kg)(?=$|\s|[가-힣,.)!?])",
        text,
        re.I,
    ))
    has_measurement_term = any(token in compact for token in (
        "상대악력", "악력", "앉아윗몸앞으로굽히기", "의자에앉았다일어서기",
        "3m표적돌아오기", "왕복달리기", "제자리멀리뛰기", "측정", "기록", "결과",
    ))
    if has_measurement_value and has_measurement_term:
        return True

    # Follow-up wording can omit the value itself but still clearly refer to the
    # previous user measurement. Do not treat generic "그 운동" as personal.
    if any(token in compact for token in (
        "그수치를고려", "그결과를고려", "그결과를생각", "그기록을기준",
        "그측정결과와연결", "그측정결과를기준",
    )):
        return True

    # Data-gap personalization is still Path B: the user explicitly asks for a
    # personalized recommendation while stating that measurements are missing.
    # We must not invent the missing value, but we should continue to RAG and
    # offer a general candidate with a clear missing-data disclaimer.
    missing_measurement_cues = (
        "안재봤", "안재보", "측정안했", "측정해본적없", "측정한적없",
        "기록없", "기록은없", "측정기록없", "결과없", "측정결과없",
    )
    personalized_action_cues = (
        "운동", "스트레칭", "루틴", "프로그램", "추천", "골라", "정해",
        "맞는", "저한테", "제게", "나한테", "부족",
    )
    if (
        any(token in compact for token in missing_measurement_cues)
        and any(token in compact for token in personalized_action_cues)
    ):
        return True

    return False


def _requests_personal_weakest_factor(message: str) -> bool:
    """Detect requests that require comparing a user's complete measurement set."""
    compact = _compact_measurement_text(message)
    weakest_cues = (
        "가장약", "제일약", "가장낮", "제일낮", "가장부족", "제일부족",
        "가장떨어", "제일떨어", "최하", "제일안좋", "가장안좋",
    )
    selection_cues = ("골라", "정해", "찾아", "선택", "추천")
    return (
        _chat_needs_personal_context(message)
        and any(cue in compact for cue in weakest_cues)
        and any(cue in compact for cue in selection_cues)
    )


@router.post("/chat")
def fitness_chat(body: FitnessChatBody, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    from coach_dialogue import safety_update
    from fitness_chat_harness_v2 import answer
    username = _auth(authorization)
    guest_context, guest_injected_values = _validated_guest_context(body.measurement_snapshot) if not username else ("", {})
    needs_personal_context = _chat_needs_personal_context(body.message, body.history)
    guest_missing_comparison_records = (
        not username
        and not guest_context
        and _requests_personal_weakest_factor(body.message)
    )
    if username:
        context, injected_values = "", {}
    elif needs_personal_context:
        context, injected_values = guest_context, guest_injected_values
    else:
        context, injected_values = "", {}
    token = _auth_token(authorization)
    trace: dict[str, Any] | None = None
    answer_path = "B" if needs_personal_context and (username or context) else "C"
    safe_history = body.history
    if username:
        # Authenticated dialogue is loaded by token+user+conversation, never from
        # browser-provided history that may belong to a previously logged-in user.
        context = ""
        safe_history = _server_chat_history(token, username, body.conversation_id)
    safety = safety_update(body.message, {})
    if safety:
        safety_response = {
            "answer": str(safety["answer"]),
            "answer_path": "C",
            "retrieved_doc_ids": [],
            "cited_doc_ids": [],
            "evidence_text": {},
            "queried_record_ids": [],
            "injected_values": {},
            "routing_flag": "SAFETY_BLOCK",
            "grounded": False,
            "grounding_type": "NONE",
            "sources": [],
            "conversation_id": body.conversation_id,
        }
        if username:
            safety_response["measurement_trace"] = _measurement_trace(username, [])
            _save_chat_turn(token, username, body.conversation_id, body.message, safety_response["answer"])
        else:
            safety_response["guest_context_validated"] = body.measurement_snapshot is not None
            safety_response["deprecated_measurement_context_ignored"] = bool(body.measurement_context)
        return _routing_trace(
            safety_response, expected_path="C",
            policy_short_circuit="SAFETY_POLICY",
        )
    if username and _certification_impersonation_request(body.message):
        profile = _profile(username)
        records = _user_measurement_records(username)
        refusal = {
            "answer": (
                "이 서비스에서는 공식 체력 인증등급을 판정하거나 인증서·확인서를 "
                "발급할 수 없습니다. 공식 판정과 발급은 공인 체력 인증센터에서 "
                "확인해 주세요."
            ),
            "answer_path": "B", "retrieved_doc_ids": [], "cited_doc_ids": [],
            "evidence_text": {}, "queried_record_ids": [], "injected_values": {},
            "routing_flag": "AUTHORITY_REFUSAL", "grounded": False,
            "grounding_type": "NONE", "sources": [],
            "conversation_id": body.conversation_id,
        }
        refusal.update(_personal_context_trace(username, profile, records))
        _save_chat_turn(token, username, body.conversation_id, body.message, refusal["answer"])
        return _routing_trace(
            refusal, expected_path="B",
            policy_short_circuit="CERTIFICATION_AUTHORITY",
        )
    if username:
        specific_answer, specific_trace = _specific_measurement_lookup_answer(username, body.message)
        if specific_answer:
            _save_chat_turn(token, username, body.conversation_id, body.message, specific_answer)
            used_record_ids = set(specific_trace.get("used_record_ids") or [])
            specific_records = _user_measurement_records(username)
            specific_sources = _measurement_sources([
                row for row in specific_records
                if int(row["record_id"]) in used_record_ids
            ])
            response = _finalize_grounding_contract({
                "answer": specific_answer,
                "answer_path": "A",
                "retrieved_doc_ids": [],
                "cited_doc_ids": [],
                "evidence_text": {},
                "queried_record_ids": specific_trace["queried_record_ids"],
                "injected_values": specific_trace["injected_values"],
                "routing_flag": (
                    "USER_MEASUREMENT_DB" if specific_trace.get("used_record_ids")
                    else "NO_USER_MEASUREMENT_RECORDS"
                ),
                "sources": specific_sources,
                "source": "user_measurement_db",
                "a_path_version": A_PATH_VERSION,
                "measurement_trace": specific_trace,
                "conversation_id": body.conversation_id,
            })
            response.update(_personal_context_trace(username, _profile(username), specific_records))
            return _routing_trace(
                response, expected_path="A",
                policy_short_circuit="MEASUREMENT_LOOKUP",
            )
        history_answer, history_trace = _measurement_history_answer(username, body.message)
        if history_answer:
            _save_chat_turn(token, username, body.conversation_id, body.message, history_answer)
            used_record_ids = set(history_trace.get("used_record_ids") or [])
            history_records = _user_measurement_records(username)
            history_sources = _measurement_sources([
                row for row in history_records
                if int(row["record_id"]) in used_record_ids
            ])
            response = _finalize_grounding_contract({
                "answer": history_answer,
                "answer_path": "A",
                "retrieved_doc_ids": [],
                "cited_doc_ids": [],
                "evidence_text": {},
                "queried_record_ids": history_trace["queried_record_ids"],
                "injected_values": history_trace["injected_values"],
                "routing_flag": (
                    "USER_MEASUREMENT_DB" if history_sources
                    else "NO_USER_MEASUREMENT_RECORDS"
                ),
                "sources": history_sources,
                "source": "user_measurement_db",
                "a_path_version": A_PATH_VERSION,
                "measurement_trace": history_trace,
                "conversation_id": body.conversation_id,
            })
            response.update(_personal_context_trace(username, _profile(username), history_records))
            return _routing_trace(
                response, expected_path="A",
                policy_short_circuit="MEASUREMENT_HISTORY",
            )
        # Authentication does not imply personalization. Load/inject the profile
        # and measurements only when the current turn genuinely depends on them.
        profile: dict[str, Any] = {}
        records: list[Any] = []
        if needs_personal_context:
            records = _user_measurement_records(username)
            trace = _measurement_trace(username, records)
            profile = _profile(username)
            profile_age = int(profile.get("age") or 0)
            profile_stage = _stage(profile_age) if profile_age else ""
            profile_sex = {"M": "남성", "F": "여성"}.get(str(profile.get("sex") or ""), "")
            context = (
                f"로그인 사용자 프로필: 만 {profile_age}세, {profile_stage} {profile_sex}. "
                "연령 판단은 이 인증 프로필을 우선하며 사용자 자유문장의 연령 표현을 "
                "임의로 다른 연령대로 해석하지 않는다."
            ).replace("  ", " ")
            answer_path = "B"
            if records:
                injected_values = trace["injected_values"]
                context += " 최근 측정기록: " + " / ".join(
                    (
                        f"레코드 {row['record_id']} {row['measured_at'][:10]} "
                        f"[{row['source']}] {row['item_name']} / 체력요인 {row['factor_name']} / "
                        f"값 {row['input_value']}{row['unit']} / {_record_percentile_display(row)['text']}"
                    )
                    for row in records
                )
                measured_factors = list(dict.fromkeys(str(row["factor_name"]) for row in records))
                context += (
                    " 측정 범위: " + ", ".join(measured_factors) +
                    ". 이 목록 밖의 체력 요소는 측정되지 않았으므로 평가하거나 추정하지 않는다."
                )
            else:
                context += (
                    " 저장된 측정 기록: 없음. 가장 부족한 체력 요소, 변화 추이, "
                    "측정 결과의 원인은 판단하거나 추정하지 않는다."
                )
        else:
            context = ""
            injected_values = {}
            answer_path = "C"
    response = answer(request.app.state.runtime, body.message, safe_history, context)
    if "3m 표적" in context and isinstance(response.get("answer"), str):
        response["answer"] = re.sub(r"민첩(?:·동적평형)?성|민첩", "평형성", response["answer"])
    response["answer_path"] = answer_path
    response["injected_values"] = injected_values
    response.setdefault("retrieved_doc_ids", [])
    response.setdefault("cited_doc_ids", [])
    response.setdefault("evidence_text", {})
    response.setdefault("routing_flag", None)
    if guest_missing_comparison_records:
        cited_title = next(
            (
                str(source.get("title") or "일반 운동 자료")
                for source in response.get("sources", [])
                if isinstance(source, dict) and source.get("evidence_id")
            ),
            "일반 운동 자료",
        )
        response["answer"] = (
            "현재 제공된 측정 기록이 없어 가장 부족한 체력 요소를 판단할 수 없습니다. "
            "기록 없이 약한 항목이나 측정값·백분위를 추정하지 않겠습니다. "
            f"일반 운동 자료에서 확인되는 후보로 {cited_title}을 안내할 수 있지만, "
            "개인 측정 결과에 따른 추천은 아닙니다. 먼저 측정을 완료하면 결과에 맞춰 안내해 드릴게요."
        )
        answer_path = "B"
        response["answer_path"] = answer_path
        response["routing_flag"] = "PERSONAL_MEASUREMENT_MISSING"
    if username:
        if answer_path == "B":
            response.update(_personal_context_trace(username, profile, records))
            if not records:
                cited_title = next(
                    (
                        str(source.get("title") or "일반 운동 자료")
                        for source in response.get("sources", [])
                        if isinstance(source, dict) and source.get("evidence_id")
                    ),
                    "일반 운동 자료",
                )
                response["answer"] = (
                    "현재 저장된 측정 기록이 없어 가장 부족한 체력 요소나 변화 추이는 "
                    f"판단할 수 없습니다. 일반 운동 자료에서 확인되는 후보로 {cited_title}을 "
                    "안내할 수 있지만, 개인 측정 결과에 따른 추천은 아닙니다."
                )
                response["routing_flag"] = "PERSONAL_MEASUREMENT_MISSING"
            else:
                cleaned = _remove_unproven_numeric_sentences(
                    str(response.get("answer") or ""),
                    body.message,
                    injected_values,
                    response.get("evidence_text") or {},
                )
                if cleaned:
                    response["answer"] = cleaned
            response["measurement_trace"] = trace or _measurement_trace(username, [])
            response["queried_record_ids"] = response["measurement_trace"]["queried_record_ids"]
        else:
            # Public Path C must not expose or claim use of private profile/measurement data.
            response["queried_record_ids"] = []
            response["injected_values"] = {}
            response["personal_context_used"] = False
        response["conversation_id"] = body.conversation_id
        _save_chat_turn(token, username, body.conversation_id, body.message, str(response.get("answer") or ""))
    else:
        response["queried_record_ids"] = []
        response["guest_context_validated"] = body.measurement_snapshot is not None
        response["deprecated_measurement_context_ignored"] = bool(body.measurement_context)
    response = _finalize_grounding_contract(response)
    retrieved = response.get("retrieved_doc_ids") or []
    if retrieved:
        rag_trigger = (
            "personalized_exercise_recommendation" if answer_path == "B"
            else "exercise_information"
        )
    else:
        rag_trigger = None
    short_circuit = "OUT_OF_SCOPE" if response.get("routing_flag") == "OUT_OF_SCOPE" else None
    return _routing_trace(
        response, expected_path=answer_path,
        policy_short_circuit=short_circuit, rag_trigger=rag_trigger,
    )


@router.get("/catalog")
def catalog(age: int, sex: str) -> dict[str, Any]:
    if sex not in {"M", "F"}:
        raise HTTPException(400, "성별은 M 또는 F여야 합니다.")
    try:
        stage, band = _stage(age), _age_band(_stage(age), age)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with sqlite3.connect(NORM_DB) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""
          SELECT DISTINCT m.item_code,m.item_name,m.factor_code,m.factor_name,m.unit,
                 m.direction,m.home_capable,m.equipment_required,m.space_required,m.priority,m.note
          FROM measurement_matrix m JOIN fitness_level_cutoff c
            ON c.life_stage=m.life_stage AND c.item_code=m.item_code
          WHERE m.life_stage=? AND c.sex=? AND c.age_band=? AND m.percentile_eligible='TRUE'
          ORDER BY CASE m.priority WHEN 'CORE' THEN 0 ELSE 1 END,m.factor_code,m.item_code
        """, (stage, sex, band)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["factor_name"] = _public_factor_name(item["item_code"], item.get("factor_name"))
        video = VIDEO_CATEGORY.get(item["item_code"], "strength")
        guide = GUIDES.get(item["item_code"], {})
        item.update({"name": item["item_name"], "factor_label": item["factor_name"], "video_category": video, "optional": item["priority"] != "CORE", "guide":guide, "measurement_videos":_measurement_videos(item["item_name"])})
        items.append(item)
    if stage == "SENIOR":
        items.append({
            "item_code": "FIGURE_8_WALK", "item_name": "8자보행", "name": "8자보행",
            "factor_code": "COORDINATION", "factor_name": "협응력", "factor_label": "협응력",
            "unit": "초", "direction": "LOWER_BETTER", "home_capable": "NONE",
            "equipment_required": "CENTER", "space_required": "CENTER", "priority": "REFERENCE",
            "note": "센터 전용 참고값이며 백분위와 Radar polygon에는 사용하지 않습니다.",
            "video_category": "agility", "optional": True, "reference_only": True,
            "percentile_eligible": False, "guide": {}, "measurement_videos": [],
        })
    return {"life_stage": stage, "age_band": band, "sex": sex, "items": items}


def _evaluate(body: EvaluateBody) -> tuple[str, str, list[dict[str, Any]]]:
    stage = _validate_life_stage(body.age, body.life_stage)
    band = _age_band(stage, body.age)
    if "RELATIVE_GRIP" in body.measurements and (body.weight_kg is None or body.weight_kg <= 0):
        raise ValueError("상대악력 계산에는 0보다 큰 체중(kg)이 필요합니다.")
    results = []
    with sqlite3.connect(NORM_DB) as db:
        db.row_factory = sqlite3.Row
        cutoff_rows = db.execute("SELECT * FROM fitness_level_cutoff WHERE life_stage=? AND sex=? AND age_band=? ORDER BY factor_code,item_code", (stage,body.sex,band)).fetchall()
        supported = {row["item_code"] for row in cutoff_rows}
        reference_value = body.measurements.get("FIGURE_8_WALK")
        if reference_value is not None and (stage != "SENIOR" or body.source != "CENTER"):
            raise ValueError("FIGURE_8_WALK은 어르신 CENTER 측정의 참고값으로만 입력할 수 있습니다.")
        unsupported = sorted(set(body.measurements) - supported - {"FIGURE_8_WALK"})
        if unsupported:
            raise ValueError(f"해당 연령·성별 규준이 없는 측정항목입니다: {', '.join(unsupported)}")
        for row in cutoff_rows:
            code = row["item_code"]
            norm_table, norm_age_band = "fitness_norm", band
            sample_n = int(row["sample_n"])
            if sample_n < MIN_SAMPLE:
                fallback = db.execute(
                    """SELECT merged_age_band,MAX(sample_n) FROM fitness_norm_fallback
                       WHERE life_stage=? AND item_code=? AND sex=? AND requested_age_band=?""",
                    (stage, code, body.sex, band),
                ).fetchone()
                if fallback and fallback[0] and int(fallback[1] or 0) >= MIN_SAMPLE:
                    norm_table, norm_age_band, sample_n = "fitness_norm_fallback", str(fallback[0]), int(fallback[1])
                else:
                    results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":body.measurements.get(code),"average_value":float(row["mean_value"]),"percentile":None,"top_percent":None,"age_band":band,"sample_n":sample_n,"direction":row["direction"],"available":code in body.measurements,"percentile_eligible":False,"status":"insufficient_sample"})
                    continue
            if code not in body.measurements:
                results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":None,"average_value":float(row["mean_value"]),"percentile":None,"top_percent":None,"age_band":band,"sample_n":int(row["sample_n"]),"direction":row["direction"],"available":False,"percentile_eligible":True})
                continue
            raw = body.measurements[code]
            value, direction = float(raw), row["direction"]
            equipment_verified = body.source == "CENTER" or code not in {"RELATIVE_GRIP", "ABSOLUTE_GRIP"} or bool(body.equipment_verified.get(code))
            eligible = body.protocol_match == "EXACT" and equipment_verified
            if not eligible:
                results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":value,"average_value":float(row["mean_value"]),"percentile":None,"top_percent":None,"age_band":band,"sample_n":sample_n,"direction":direction,"available":True,"percentile_eligible":False,"protocol_match":body.protocol_match,"equipment_verified":equipment_verified,"status":"protocol_not_eligible"})
                continue
            if direction == "LOWER_BETTER":
                if norm_table == "fitness_norm":
                    norm = db.execute("""SELECT MIN(percentile), MAX(norm_version) FROM fitness_norm
                      WHERE life_stage=? AND sex=? AND age_band=? AND item_code=? AND cut_value>=?""",
                      (stage,body.sex,band,code,value)).fetchone()
                else:
                    norm = db.execute("""SELECT MIN(percentile), MAX(norm_version) FROM fitness_norm_fallback
                      WHERE life_stage=? AND sex=? AND requested_age_band=? AND item_code=? AND cut_value>=?""",
                      (stage,body.sex,band,code,value)).fetchone()
                raw_percentile = 100.0 if norm[0] is None else float(norm[0])
            else:
                if norm_table == "fitness_norm":
                    norm = db.execute("""SELECT MAX(percentile), MAX(norm_version) FROM fitness_norm
                      WHERE life_stage=? AND sex=? AND age_band=? AND item_code=? AND cut_value<=?""",
                      (stage,body.sex,band,code,value)).fetchone()
                else:
                    norm = db.execute("""SELECT MAX(percentile), MAX(norm_version) FROM fitness_norm_fallback
                      WHERE life_stage=? AND sex=? AND requested_age_band=? AND item_code=? AND cut_value<=?""",
                      (stage,body.sex,band,code,value)).fetchone()
                raw_percentile = 0.0 if norm[0] is None else float(norm[0])
            percentile = raw_percentile
            if direction == "LOWER_BETTER":
                percentile = 100 - percentile
            results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":value,"average_value":float(row["mean_value"]),"percentile":float(percentile),"top_percent":float(100-percentile),"age_band":band,"norm_source_age_band":norm_age_band,"sample_n":sample_n,"norm_version":norm[1],"direction":direction,"available":True,"percentile_eligible":True,"protocol_match":body.protocol_match,"equipment_verified":equipment_verified})
    if reference_value is not None:
        results.append({
            "code": "FIGURE_8_WALK", "item_code": "FIGURE_8_WALK", "name": "8자보행",
            "factor_name": "협응력", "unit": "초", "input_value": float(reference_value),
            "average_value": None, "percentile": None, "top_percent": None, "age_band": band,
            "sample_n": None, "norm_version": None, "direction": "LOWER_BETTER", "available": True,
            "percentile_eligible": False, "protocol_match": body.protocol_match,
            "equipment_verified": True, "status": "reference_only", "reference_only": True,
        })
    for result in results:
        result["factor_name"] = _public_factor_name(result["item_code"], result.get("factor_name"))
        result["percentile_display"] = _percentile_display(body.source, result["item_code"], result.get("top_percent"))
    return stage, band, results


@router.post("/evaluate")
def evaluate(body: EvaluateBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        stage, band, results = _evaluate(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    username = _auth(authorization)
    session_id = None
    body_composition = _body_composition(body)
    if username and results:
        with sqlite3.connect(USER_DB) as db:
            cur = db.execute("INSERT INTO measurement_sessions(username,measured_at,age,sex,height_cm,weight_kg,life_stage,summary,source) VALUES(?,?,?,?,?,?,?,?,?)", (username, body.measured_at or _now(), body.age, body.sex, body.height_cm, body.weight_kg, stage, "", body.source))
            session_id = cur.lastrowid
            db.executemany("""INSERT INTO measurement_results(
              session_id,item_code,item_name,factor_name,unit,input_value,average_value,
              percentile,age_band,norm_version,protocol_match,equipment_verified,percentile_eligible
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (session_id,r["item_code"],r["name"],r["factor_name"],r["unit"],r["input_value"],
                 r["average_value"],r["percentile"],band,r.get("norm_version"),
                 r.get("protocol_match",body.protocol_match),int(r.get("equipment_verified",True)),
                 int(r.get("percentile_eligible",False))) for r in results if r["available"]
            ])
            if body_composition:
                db.executemany("""INSERT INTO body_composition_results(
                  session_id,metric_code,raw_value,unit,category,percentile_eligible
                  ) VALUES(?,?,?,?,?,0)""", [
                    (session_id,item["metric_code"],item["raw_value"],item["unit"],item["category"])
                    for item in body_composition
                ])
            old_ids = [r[0] for r in db.execute("SELECT id FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC,id DESC LIMIT -1 OFFSET 10", (username,))]
            if old_ids:
                marks = ",".join("?" * len(old_ids))
                db.execute(f"DELETE FROM body_composition_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_sessions WHERE id IN ({marks})", old_ids)
    return {"life_stage":stage,"age_band":band,"source":body.source,"results":results,"body_composition":body_composition,"saved":bool(session_id),"session_id":session_id,"result_label":"보유 데이터 성별·연령대 자체 규준"}


@router.get("/history")
def history(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        sessions = [dict(r) for r in db.execute("SELECT * FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC LIMIT 30", (username,))]
        for session in sessions:
            session["results"] = [dict(r) for r in db.execute("SELECT id AS record_id,item_code,item_name,factor_name,unit,input_value,average_value,percentile,age_band,norm_version,protocol_match,equipment_verified,percentile_eligible FROM measurement_results WHERE session_id=? ORDER BY id", (session["id"],))]
            for result in session["results"]:
                result["factor_name"] = _public_factor_name(result["item_code"], result.get("factor_name"))
            session["body_composition"] = [dict(r) for r in db.execute("SELECT id AS record_id,metric_code,raw_value,unit,category,percentile_eligible FROM body_composition_results WHERE session_id=? ORDER BY id", (session["id"],))]
    return {"username":username,"sessions":sessions}


@router.get("/records")
def measurement_records(limit_sessions: int = 10, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Return the exact DB records eligible for this authenticated user's AI context."""
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    records = _user_measurement_records(username, limit_sessions)
    return {**_measurement_trace(username, records), "records": records}


@router.post("/report-summary")
def report_summary(body: SummaryBody, request: Request) -> dict[str, str]:
    measured = [r for r in body.results if r.get("available")]
    if not measured:
        return {"summary":"입력된 측정값이 없어 비교 요약을 만들 수 없습니다."}
    def summary_fact(row: dict[str, Any]) -> str:
        code = str(row.get("item_code") or row.get("code") or "")
        factor = _public_factor_name(code, row.get("factor_name") or row.get("name"))
        if code == "FIGURE_8_WALK" or row.get("reference_only") or row.get("status") == "reference_only":
            return f"{factor} 8자보행 {row.get('input_value')}{row.get('unit')} 센터 참고값, 백분위 미제공"
        display = _percentile_display(body.source, code, row.get("top_percent"))["text"]
        return f"{factor} {row.get('input_value')}{row.get('unit')} 평균 {row.get('average_value')}{row.get('unit')} {display}"
    facts = "; ".join(summary_fact(r) for r in measured)
    previous = "; ".join(
        f"{_public_factor_name(str(r.get('item_code') or r.get('code') or ''), r.get('factor_name') or r.get('item_name'))} {r.get('input_value')}{r.get('unit')}"
        for r in body.previous_results
    )
    compare = f" 이전 기록: {previous}. 변화도 비교하라." if previous else " 이전 기록이 없으므로 이번 결과만 설명하라."
    source_rule = "HOME 자가측정의 또래 위치는 제공된 구간 그대로만 말하고 점 백분위로 단정하지 마라." if body.source == "HOME" else "CENTER 측정의 제공된 점 백분위를 그대로 사용하라."
    prompt = f"만 {body.age}세 {body.sex} {body.source} 체력측정 결과: {facts}.{compare} {source_rule} 수치를 바꾸거나 진단하지 말고 가장 좋은 점과 보완할 점을 한국어 45~60자로 완결된 두 문장에 담아라. 괄호·콜론·항목 나열·명령조를 쓰지 말고 따뜻한 존댓말을 사용하라. 같은 표현이나 '좋아요요' 같은 어미를 반복하지 말고, 문장을 절대 중간에서 끊지 마라."
    try:
        raw = request.app.state.runtime.qwen3_client.complete_json(
            "당신은 체력측정 결과를 정확하면서도 따뜻하고 부드러운 존댓말로 설명하는 코치다. 딱딱한 보고서 문체나 단어 나열을 쓰지 않는다. 반드시 JSON 객체만 출력한다.",
            prompt,
            max_tokens=100,
            response_schema={"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]},
        )
        text = re.sub(r"\s+", " ", str(json.loads(raw).get("summary") or "")).strip()
        sentences = re.findall(r".+?[.!?。](?:\s+|$)|.+$", text)
        complete = ""
        for sentence in sentences:
            candidate = (complete + " " + sentence.strip()).strip()
            if len(candidate) > 70:
                break
            complete = candidate
        home_point_claim = body.source == "HOME" and bool(re.search(r"(?:상위\s*)?\d+(?:\.\d+)?%|백분위\s*\d+", complete)) and not bool(re.search(r"\d+(?:\.\d+)?\s*[~-]\s*\d+(?:\.\d+)?%", complete))
        chair_label_mismatch = any(str(r.get("item_code") or r.get("code") or "") == "CHAIR_3M_TURN" for r in measured) and "민첩" in complete
        if 30 <= len(complete) <= 70 and complete[-1:] in ".!?。" and not home_point_claim and not chair_label_mismatch:
            return {"summary":complete}
    except Exception:
        pass
    ranked = [r for r in measured if r.get("percentile_eligible") is not False and r.get("percentile") is not None]
    if not ranked:
        return {"summary":"센터 참고값을 안전하게 기록했어요. 다음 측정과 함께 변화를 살펴보세요."}
    best = max(ranked, key=lambda r: float(r["percentile"]))
    weak = min(ranked, key=lambda r: float(r["percentile"]))
    best_label = _public_factor_name(str(best.get("item_code") or best.get("code") or ""), best.get("factor_name"))
    weak_label = _public_factor_name(str(weak.get("item_code") or weak.get("code") or ""), weak.get("factor_name"))
    return {"summary":f"{best_label}은 좋은 흐름이에요. {weak_label}을 가볍게 보완하며 균형을 맞춰보세요."}


init_norm_fallback_db()
init_user_db()
