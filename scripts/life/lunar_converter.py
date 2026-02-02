#!/usr/bin/env python3
"""
Lunar Calendar Converter - 음력/양력 변환 모듈

korean-lunar-calendar 라이브러리를 사용하여 음력 날짜를 양력으로 변환합니다.

Usage:
    from scripts.life.lunar_converter import lunar_to_solar

    # 2026년 설날 (음력 1월 1일) -> 양력
    solar_date = lunar_to_solar(2026, 1, 1)
    # 결과: date(2026, 2, 17)
"""

from datetime import date
from typing import Optional

try:
    from korean_lunar_calendar import KoreanLunarCalendar
except ImportError:
    raise ImportError(
        "korean-lunar-calendar 라이브러리가 설치되지 않았습니다.\n"
        "설치: pip install korean-lunar-calendar"
    )


def lunar_to_solar(
    year: int,
    month: int,
    day: int,
    is_leap_month: bool = False
) -> Optional[date]:
    """
    음력 날짜를 양력 날짜로 변환

    Args:
        year: 연도 (양력 연도 기준)
        month: 음력 월 (1-12)
        day: 음력 일 (1-30)
        is_leap_month: 윤달 여부 (기본: False)

    Returns:
        변환된 양력 date 객체, 실패 시 None

    Examples:
        >>> lunar_to_solar(2026, 1, 1)  # 2026년 설날
        datetime.date(2026, 2, 17)

        >>> lunar_to_solar(2026, 8, 15)  # 2026년 추석
        datetime.date(2026, 10, 3)
    """
    try:
        calendar = KoreanLunarCalendar()
        calendar.setLunarDate(year, month, day, is_leap_month)

        return date(
            calendar.solarYear,
            calendar.solarMonth,
            calendar.solarDay
        )
    except Exception:
        return None


def solar_to_lunar(
    year: int,
    month: int,
    day: int
) -> Optional[tuple[int, int, int, bool]]:
    """
    양력 날짜를 음력 날짜로 변환

    Args:
        year: 양력 연도
        month: 양력 월 (1-12)
        day: 양력 일 (1-31)

    Returns:
        (음력연도, 음력월, 음력일, 윤달여부) 튜플, 실패 시 None

    Examples:
        >>> solar_to_lunar(2026, 2, 17)  # 2026년 설날
        (2026, 1, 1, False)
    """
    try:
        calendar = KoreanLunarCalendar()
        calendar.setSolarDate(year, month, day)

        return (
            calendar.lunarYear,
            calendar.lunarMonth,
            calendar.lunarDay,
            calendar.isIntercalation  # 윤달 여부
        )
    except Exception:
        return None


def get_lunar_new_year(year: int) -> Optional[date]:
    """
    해당 연도의 설날(음력 1월 1일) 양력 날짜 반환

    Args:
        year: 연도

    Returns:
        설날 양력 날짜
    """
    return lunar_to_solar(year, 1, 1)


def get_chuseok(year: int) -> Optional[date]:
    """
    해당 연도의 추석(음력 8월 15일) 양력 날짜 반환

    Args:
        year: 연도

    Returns:
        추석 양력 날짜
    """
    return lunar_to_solar(year, 8, 15)


if __name__ == "__main__":
    # 테스트 실행
    import sys

    print("=== 음력/양력 변환 테스트 ===\n")

    # 2026년 명절 테스트
    seollal_2026 = lunar_to_solar(2026, 1, 1)
    chuseok_2026 = lunar_to_solar(2026, 8, 15)

    print(f"2026년 설날 (음력 1/1): {seollal_2026}")
    print(f"2026년 추석 (음력 8/15): {chuseok_2026}")

    # 2027년 명절 테스트
    seollal_2027 = lunar_to_solar(2027, 1, 1)
    chuseok_2027 = lunar_to_solar(2027, 8, 15)

    print(f"\n2027년 설날 (음력 1/1): {seollal_2027}")
    print(f"2027년 추석 (음력 8/15): {chuseok_2027}")

    # 역변환 테스트
    if seollal_2026:
        result = solar_to_lunar(seollal_2026.year, seollal_2026.month, seollal_2026.day)
        print(f"\n역변환 테스트: {seollal_2026} -> 음력 {result}")

    sys.exit(0)
