"""국민연령별추천운동정보 CSV를 배포용 조건 조회 DB로 만든다."""

from __future__ import annotations

import argparse
from pathlib import Path

from age_bmi_recommendations import build_rule_database, rule_status


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT / "source_data" / "KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "age_bmi_recommendation_rules.sqlite",
    )
    args = parser.parse_args()
    report = build_rule_database(args.source, args.target)
    status = rule_status(args.target)
    if not status.get("available"):
        raise RuntimeError(f"생성한 규칙 DB 검증 실패: {status}")
    print({**report, "database": str(args.target), "status": status})


if __name__ == "__main__":
    main()
