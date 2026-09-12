"""MVP authentication, measurement catalogue, percentile evaluation, and history."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Path(__file__).resolve().parents[3]
VIDEO_DIR = REPO_ROOT / "data" / "reference" / "videos"
NORM_DB = Path(os.environ.get("AI_FITNESS_NORM_DB", str(PROJECT_ROOT / "artifacts" / "fitness_percentile.db")))
USER_DB = Path(os.environ.get("AI_FITNESS_USER_DB", str(PROJECT_ROOT / "runtime" / "fitness_user_records.db")))
MEASURE_VIDEO_JSON = VIDEO_DIR / "02_체력인증측정방법.json"
ALL_VIDEO_JSON = VIDEO_DIR / "07_동영상전체목록.json"
STANDARD_VIDEO_JSON = VIDEO_DIR / "05_생애주기별표준운동.json"
ROUTINE_VIDEO_JSON = VIDEO_DIR / "06_목적별루틴운동.json"
router = APIRouter(prefix="/api/mvp", tags=["fitness-mvp"])


ITEM_UI = {
    "CURL_UP": ("윗몸말아올리기", "근지구력", "endurance"),
    "CROSS_SIT_UP": ("교차윗몸일으키기", "근지구력", "endurance"),
    "SIT_AND_REACH": ("앉아윗몸앞으로굽히기", "유연성", "flexibility"),
    "STANDING_LONG_JUMP": ("제자리멀리뛰기", "순발력", "power"),
    "RELATIVE_GRIP": ("상대악력", "근력", "grip"),
    "ABSOLUTE_GRIP": ("악력", "근력", "grip"),
    "SHUTTLE_RUN_10M": ("10m 왕복오래달리기", "심폐지구력", "cardio"),
    "SHUTTLE_RUN_15M": ("15m 왕복오래달리기", "심폐지구력", "cardio"),
    "SHUTTLE_RUN_20M": ("20m 왕복오래달리기", "심폐지구력", "cardio"),
    "SHUTTLE_RUN_5M_X4": ("5m×4 왕복달리기", "민첩성", "agility"),
    "SIDE_STEP": ("반복옆뛰기", "민첩성", "agility"),
    "CHAIR_STAND_30S": ("30초 의자 일어서기", "하지근기능", "strength"),
    "STEP_IN_PLACE_2MIN": ("2분 제자리걷기", "심폐지구력", "cardio"),
    "CHAIR_3M_TURN": ("의자에서 일어나 3m 돌아오기", "민첩·평형성", "agility"),
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
          summary TEXT, FOREIGN KEY(username) REFERENCES users(username)
        );
        CREATE TABLE IF NOT EXISTS measurement_results(
          id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
          item_code TEXT NOT NULL, item_name TEXT NOT NULL, factor_name TEXT NOT NULL,
          unit TEXT NOT NULL, input_value REAL NOT NULL, average_value REAL,
          percentile REAL, level_code TEXT, level_name TEXT, age_band TEXT,
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
        """)
        existing = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        for name, declaration in (("age","INTEGER"),("height_cm","REAL"),("weight_kg","REAL"),("profile_completed","INTEGER NOT NULL DEFAULT 0")):
            if name not in existing:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {declaration}")
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
                db.execute(f"DELETE FROM measurement_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_sessions WHERE id IN ({marks})", old_ids)


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


def _age_band(stage: str, age: int) -> str:
    if stage == "PRESCHOOL":
        months = age * 12
        return next((b for b, lo, hi in (("48-53M",48,53),("54-59M",54,59),("60-65M",60,65),("66-71M",66,71),("72-83M",72,83)) if lo <= months <= hi), "72-83M")
    if stage in {"CHILD", "TEEN"}:
        return str(age)
    bands = (("19-24",19,24),("25-29",25,29),("30-34",30,34),("35-39",35,39),("40-44",40,44),("45-49",45,49),("50-54",50,54),("55-59",55,59),("60-64",60,64)) if stage == "ADULT" else (("65-69",65,69),("70-74",70,74),("75-79",75,79),("80-84",80,84),("85+",85,200))
    return next(b for b, lo, hi in bands if lo <= age <= hi)


def _auth(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    with sqlite3.connect(USER_DB) as db:
        row = db.execute("SELECT username FROM auth_sessions WHERE token=?", (authorization[7:],)).fetchone()
    return row[0] if row else None


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class SignupBody(LoginBody):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(default="", max_length=150)
    phone: str = Field(default="", max_length=30)
    birth_date: str = Field(default="", max_length=10)
    sex: str = Field(pattern="^(M|F)$")


class EvaluateBody(BaseModel):
    age: int = Field(ge=4, le=120)
    sex: str = Field(pattern="^(M|F)$")
    height_cm: float | None = None
    weight_kg: float | None = None
    measured_at: str | None = None
    measurements: dict[str, float] = Field(default_factory=dict)


class SummaryBody(BaseModel):
    age: int
    sex: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    previous_results: list[dict[str, Any]] = Field(default_factory=list)


class FitnessChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)
    measurement_context: str = Field(default="", max_length=3000)


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(default="", max_length=150)
    phone: str = Field(default="", max_length=30)
    birth_date: str = Field(default="", max_length=10)
    sex: str = Field(pattern="^(M|F)$")
    age: int = Field(ge=4, le=120)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=20, le=300)


def _measurement_history_answer(username: str, message: str, history: list[dict[str, str]]) -> str | None:
    """Answer record/trend questions from saved percentiles instead of unrelated RAG hits."""
    # Do not let an old measurement question hijack every later conversation turn.
    # Short follow-ups such as "나아지고 있어?" already contain an explicit trend cue.
    if not any(word in message for word in ("기록", "측정 결과", "나아", "향상", "변화", "추이", "좋아졌", "개선")):
        return None
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        sessions = db.execute(
            "SELECT id,measured_at FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC,id DESC LIMIT 10",
            (username,),
        ).fetchall()
        snapshots: list[tuple[sqlite3.Row, dict[str, sqlite3.Row]]] = []
        for session in sessions:
            values = db.execute(
                "SELECT item_code,input_value,unit,percentile,level_name FROM measurement_results WHERE session_id=?",
                (session["id"],),
            ).fetchall()
            if values:
                snapshots.append((session, {row["item_code"]: row for row in values}))
    if not snapshots:
        return "아직 저장된 측정 기록이 없어요. 먼저 측정을 완료하면 이전 기록과 비교해 드릴게요."

    latest_session, latest = snapshots[0]
    previous_pair = next(((s, v) for s, v in snapshots[1:] if set(v) & set(latest)), None)
    label = lambda code: ITEM_UI.get(code, (code, code, ""))[0]
    if not previous_pair:
        names = ", ".join(dict.fromkeys(label(code) for code in latest))
        return f"{latest_session['measured_at'][:10]}에 저장된 첫 측정이에요. {names} 기록을 기준점으로 보관했으니 다음 측정부터 변화 폭을 함께 보여드릴게요."

    previous_session, previous = previous_pair
    changes = []
    for code, now in latest.items():
        old = previous.get(code)
        if old is None or now["percentile"] is None or old["percentile"] is None:
            continue
        changes.append((float(now["percentile"]) - float(old["percentile"]), label(code)))
    if not changes:
        return "최근 기록은 확인했지만 같은 항목의 백분위가 있는 이전 측정이 없어 아직 변화량을 계산하기 어려워요. 한 번 더 측정하면 비교해 드릴게요."

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
        best = improved[0] if improved else max(changes)
        caution = declined[0] if declined else None
        detail = f" 특히 {best[1]} 기록이 이전보다 {abs(best[0]):.0f}%p 좋아졌어요."
        if caution:
            detail += f" 다만 {caution[1]} 기록은 {abs(caution[0]):.0f}%p 내려가 다음 측정도 함께 지켜보면 좋겠어요."
        return opening + detail
    return opening + " " + ". ".join(parts) + ". 같은 조건에서 다시 측정하면 흐름을 더 정확히 볼 수 있어요."


def _profile(username: str) -> dict[str, Any]:
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT username,name,email,phone,birth_date,sex,age,height_cm,weight_kg,profile_completed FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else {}


@router.post("/login")
def login(body: LoginBody) -> dict[str, Any]:
    with sqlite3.connect(USER_DB) as db:
        row = db.execute("SELECT password_hash,salt,name FROM users WHERE username=?", (body.username,)).fetchone()
    if not row or not secrets.compare_digest(row[0], _hash(body.password, row[1])):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    token = secrets.token_urlsafe(32)
    with sqlite3.connect(USER_DB) as db:
        db.execute("INSERT INTO auth_sessions(token,username,created_at) VALUES(?,?,?)", (token, body.username, _now()))
    return {"token": token, "username": body.username, "name": row[2], "profile": _profile(body.username)}


@router.post("/signup")
def signup(body: SignupBody) -> dict[str, str]:
    salt = secrets.token_hex(12)
    try:
        with sqlite3.connect(USER_DB) as db:
            db.execute("INSERT INTO users(username,password_hash,salt,name,email,phone,birth_date,sex,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (body.username, _hash(body.password, salt), salt, body.name, body.email, body.phone, body.birth_date, body.sex, _now()))
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
        db.execute("UPDATE users SET name=?,email=?,phone=?,birth_date=?,sex=?,age=?,height_cm=?,weight_kg=?,profile_completed=1 WHERE username=?", (body.name,body.email,body.phone,body.birth_date,body.sex,body.age,body.height_cm,body.weight_kg,username))
    return _profile(username)


def _measurement_videos(item_name: str) -> list[dict[str, Any]]:
    if not MEASURE_VIDEO_JSON.is_file():
        return []
    try:
        items = json.loads(MEASURE_VIDEO_JSON.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        return []
    aliases = {"상대악력":"악력","절대악력":"악력","10m 4회 왕복달리기":"왕복달리기","10m 왕복오래달리기":"왕복오래달리기","15m 왕복오래달리기":"왕복오래달리기","20m 왕복오래달리기":"왕복오래달리기","의자에앉아 3m 표적돌아오기":"3m","의자에앉았다일어서기":"의자"}
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


def _training_videos(item_code: str, age: int, current_level: str) -> dict[str, Any]:
    level_order = ["최하위","하위","중위","상위","최상위"]
    next_level = level_order[min(level_order.index(current_level) + 1, 4)] if current_level in level_order else "상위"
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
    target_week = {"최하위":"1주차","하위":"1주차","중위":"2주차","상위":"3주차","최상위":"4주차"}.get(next_level,"3주차")
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
    return {"item_code":item_code,"current_level":current_level,"target_level":next_level,"target_week":target_week,"videos":selected}


@router.get("/recommendation-videos/{item_code}")
def recommendation_videos(item_code: str, age: int, level: str = "중위") -> dict[str, Any]:
    return _training_videos(item_code, age, level)


@router.post("/chat")
def fitness_chat(body: FitnessChatBody, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    from fitness_chat_harness_v2 import answer
    context = body.measurement_context
    username = _auth(authorization)
    if username:
        history_answer = _measurement_history_answer(username, body.message, body.history)
        if history_answer:
            return {"answer": history_answer, "grounded": True, "source": "user_measurement_db"}
        personal_question = any(word in body.message for word in ("내 ", "나의", "제 ", "추천", "체력", "약점", "강점", "백분위"))
        if personal_question:
            with sqlite3.connect(USER_DB) as db:
                rows = db.execute("""SELECT s.measured_at,r.item_code,r.input_value,r.unit,r.percentile,r.level_name
                  FROM measurement_sessions s JOIN measurement_results r ON r.session_id=s.id
                  WHERE s.username=? ORDER BY s.measured_at DESC,s.id DESC,r.id LIMIT 60""", (username,)).fetchall()
            if rows:
                context = "로그인 사용자의 최근 측정기록(백분위는 높을수록 좋음): " + " / ".join(
                    f"{date[:10]} {ITEM_UI.get(code,(code,code,''))[1]} {value}{unit} 백분위 {percentile} {level}"
                    for date,code,value,unit,percentile,level in rows
                )
        else:
            context = ""
    return answer(request.app.state.runtime, body.message, body.history, context)


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
        label, _fallback_factor, video = ITEM_UI.get(item["item_code"], (item["item_name"], item["factor_name"], "strength"))
        guide = GUIDES.get(item["item_code"], {})
        item.update({"name": label, "factor_label": item["factor_name"], "video_category": video, "optional": item["priority"] != "CORE", "guide":guide, "measurement_videos":_measurement_videos(item["item_name"])})
        items.append(item)
    return {"life_stage": stage, "age_band": band, "sex": sex, "items": items}


def _evaluate(body: EvaluateBody) -> tuple[str, str, list[dict[str, Any]]]:
    stage, band = _stage(body.age), _age_band(_stage(body.age), body.age)
    results = []
    with sqlite3.connect(NORM_DB) as db:
        db.row_factory = sqlite3.Row
        cutoff_rows = db.execute("SELECT * FROM fitness_level_cutoff WHERE life_stage=? AND sex=? AND age_band=? ORDER BY factor_code,item_code", (stage,body.sex,band)).fetchall()
        for row in cutoff_rows:
            code = row["item_code"]
            if code not in body.measurements:
                results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":None,"average_value":float(row["mean_value"]),"percentile":None,"top_percent":None,"score":None,"average_score":50.0,"level_code":None,"level_name":"미측정","age_band":band,"sample_n":int(row["sample_n"]),"direction":row["direction"],"available":False})
                continue
            raw = body.measurements[code]
            value, direction = float(raw), row["direction"]
            cuts = [float(row[f"p{p}_value"]) for p in (20,40,60,80)]
            if direction == "HIGHER_BETTER":
                level = 5 if value >= cuts[3] else 4 if value >= cuts[2] else 3 if value >= cuts[1] else 2 if value >= cuts[0] else 1
            else:
                level = 5 if value <= cuts[0] else 4 if value <= cuts[1] else 3 if value <= cuts[2] else 2 if value <= cuts[3] else 1
            norms = db.execute("SELECT percentile,cut_value FROM fitness_norm WHERE life_stage=? AND sex=? AND age_band=? AND item_code=? ORDER BY percentile", (stage, body.sex, band, code)).fetchall()
            percentile = min(norms, key=lambda n: abs(float(n["cut_value"])-value))["percentile"]
            if direction == "LOWER_BETTER":
                percentile = 100 - percentile
            level_names = {5:"최상위",4:"상위",3:"중위",2:"하위",1:"최하위"}
            results.append({"code":code,"item_code":code,"name":row["item_name"],"factor_name":row["factor_name"],"unit":row["unit"],"input_value":value,"average_value":float(row["mean_value"]),"percentile":float(percentile),"top_percent":float(100-percentile),"score":float(percentile),"average_score":50.0,"level_code":level,"level_name":level_names[level],"age_band":band,"sample_n":int(row["sample_n"]),"direction":direction,"available":True})
    return stage, band, results


@router.post("/evaluate")
def evaluate(body: EvaluateBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        stage, band, results = _evaluate(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    username = _auth(authorization)
    session_id = None
    if username and results:
        with sqlite3.connect(USER_DB) as db:
            cur = db.execute("INSERT INTO measurement_sessions(username,measured_at,age,sex,height_cm,weight_kg,life_stage,summary) VALUES(?,?,?,?,?,?,?,?)", (username, body.measured_at or _now(), body.age, body.sex, body.height_cm, body.weight_kg, stage, ""))
            session_id = cur.lastrowid
            db.executemany("INSERT INTO measurement_results(session_id,item_code,item_name,factor_name,unit,input_value,average_value,percentile,level_code,level_name,age_band) VALUES(?,?,?,?,?,?,?,?,?,?,?)", [(session_id,r["item_code"],r["name"],r["factor_name"],r["unit"],r["input_value"],r["average_value"],r["percentile"],str(r["level_code"]),r["level_name"],band) for r in results if r["available"]])
            old_ids = [r[0] for r in db.execute("SELECT id FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC,id DESC LIMIT -1 OFFSET 10", (username,))]
            if old_ids:
                marks = ",".join("?" * len(old_ids))
                db.execute(f"DELETE FROM measurement_results WHERE session_id IN ({marks})", old_ids)
                db.execute(f"DELETE FROM measurement_sessions WHERE id IN ({marks})", old_ids)
    return {"life_stage":stage,"age_band":band,"results":results,"saved":bool(session_id),"session_id":session_id,"result_label":"보유 데이터 성별·연령대 자체 규준"}


@router.get("/history")
def history(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    username = _auth(authorization)
    if not username:
        raise HTTPException(401, "로그인이 필요합니다.")
    with sqlite3.connect(USER_DB) as db:
        db.row_factory = sqlite3.Row
        sessions = [dict(r) for r in db.execute("SELECT * FROM measurement_sessions WHERE username=? ORDER BY measured_at DESC LIMIT 30", (username,))]
        for session in sessions:
            session["results"] = [dict(r) for r in db.execute("SELECT item_code,item_name,factor_name,unit,input_value,average_value,percentile,level_name,age_band FROM measurement_results WHERE session_id=? ORDER BY id", (session["id"],))]
    return {"username":username,"sessions":sessions}


@router.post("/report-summary")
def report_summary(body: SummaryBody, request: Request) -> dict[str, str]:
    measured = [r for r in body.results if r.get("available")]
    if not measured:
        return {"summary":"입력된 측정값이 없어 비교 요약을 만들 수 없습니다."}
    facts = "; ".join(f"{r.get('factor_name') or r.get('name')} {r.get('input_value')}{r.get('unit')} 평균 {r.get('average_value')}{r.get('unit')} {r.get('level_name')}" for r in measured)
    previous = "; ".join(f"{r.get('factor_name') or r.get('item_name')} {r.get('input_value')}{r.get('unit')}" for r in body.previous_results)
    compare = f" 이전 기록: {previous}. 변화도 비교하라." if previous else " 이전 기록이 없으므로 이번 결과만 설명하라."
    prompt = f"만 {body.age}세 {body.sex} 체력측정 결과: {facts}.{compare} 수치를 바꾸거나 진단하지 말고 강점, 보완점, 다음 행동을 포함해 한국어 약 100자(80~120자)로 써라. 괄호·콜론·항목 나열·명령조를 쓰지 말고, 사용자를 응원하며 '~해보세요', '~하면 좋아요' 같은 자연스러운 존댓말로 이어서 말하라. 최하위처럼 차갑게 들리는 등급명은 반복하지 말고 '조금 더 보완하면 좋아요'처럼 풀어서 설명하라."
    try:
        raw = request.app.state.runtime.qwen3_client.complete_json(
            "당신은 체력측정 결과를 정확하면서도 따뜻하고 부드러운 존댓말로 설명하는 코치다. 딱딱한 보고서 문체나 단어 나열을 쓰지 않는다. 반드시 JSON 객체만 출력한다.",
            prompt,
            max_tokens=180,
            response_schema={"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]},
        )
        text = str(json.loads(raw).get("summary") or "").strip()
        if 60 <= len(text) <= 140:
            return {"summary":text[:120]}
    except Exception:
        pass
    best = max(measured, key=lambda r: float(r.get("percentile") or 0))
    weak = min(measured, key=lambda r: float(r.get("percentile") or 0))
    return {"summary":f"{best.get('factor_name')}이 좋은 강점으로 나타났어요. {weak.get('factor_name')}은 조금 더 키워갈 여지가 있으니, 부담 없는 동작부터 천천히 연습하며 다음 변화를 확인해보세요."[:120]}


init_user_db()
