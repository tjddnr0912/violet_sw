#!/usr/bin/env python3
"""
Nonce 관리 및 시간 동기화 시스템
"""

import time
import secrets
import threading
import ntplib
import logging
from datetime import datetime, timedelta
from typing import Set, Optional
import sqlite3
import os

class NonceManager:
    def __init__(self, db_path: str = "nonce_history.db"):
        self.db_path = db_path
        self.used_nonces: Set[str] = set()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self.time_offset = 0  # NTP 서버와의 시간 차이

        # 데이터베이스 초기화
        self._init_database()

        # 시간 동기화 확인
        self._check_time_sync()

    def _init_database(self):
        """Nonce 이력 관리용 데이터베이스 초기화"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS nonce_history (
                        nonce TEXT PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        used_at TIMESTAMP
                    )
                ''')

                # 7일 이상 된 기록 삭제
                conn.execute('''
                    DELETE FROM nonce_history
                    WHERE created_at < datetime('now', '-7 days')
                ''')
                conn.commit()

        except Exception as e:
            self.logger.error(f"데이터베이스 초기화 실패: {e}")

    def _check_time_sync(self):
        """NTP 서버와 시간 동기화 확인"""
        try:
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request('pool.ntp.org', version=3, timeout=5)

            ntp_time = datetime.fromtimestamp(response.tx_time)
            local_time = datetime.now()

            self.time_offset = (ntp_time - local_time).total_seconds()

            if abs(self.time_offset) > 30:  # 30초 이상 차이
                self.logger.warning(f"시간 동기화 문제 감지: {self.time_offset:.2f}초 차이")
            else:
                self.logger.info(f"시간 동기화 확인: {self.time_offset:.2f}초 차이")

        except Exception as e:
            self.logger.warning(f"NTP 동기화 확인 실패: {e}")
            self.time_offset = 0

    def get_synchronized_timestamp(self) -> float:
        """동기화된 타임스탬프 반환"""
        return time.time() + self.time_offset

    def generate_nonce(self) -> str:
        """고유한 Nonce 생성"""
        with self.lock:
            max_attempts = 100

            for attempt in range(max_attempts):
                # 마이크로초 정밀도로 타임스탬프 생성
                timestamp = int(self.get_synchronized_timestamp() * 1000000)

                # 추가 랜덤성 보장
                random_part = secrets.randbits(32)  # 32비트 랜덤

                # Nonce 조합
                nonce = f"{timestamp}{random_part:08x}"

                # 중복 확인
                if not self._is_nonce_used(nonce):
                    self._record_nonce(nonce)
                    return nonce

                # 중복일 경우 잠시 대기 후 재시도
                time.sleep(0.001)  # 1ms 대기

            raise RuntimeError(f"Nonce 생성 실패: {max_attempts}회 시도 후 중복 해결 불가")

    def _is_nonce_used(self, nonce: str) -> bool:
        """Nonce 사용 여부 확인"""
        # 메모리 캐시 확인
        if nonce in self.used_nonces:
            return True

        # 데이터베이스 확인
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM nonce_history WHERE nonce = ? LIMIT 1",
                    (nonce,)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"Nonce 중복 확인 실패: {e}")
            return True  # 안전을 위해 중복으로 가정

    def _record_nonce(self, nonce: str):
        """Nonce 사용 기록"""
        try:
            # 메모리 캐시에 추가
            self.used_nonces.add(nonce)

            # 메모리 관리 (최근 10000개만 유지)
            if len(self.used_nonces) > 10000:
                self.used_nonces.clear()

            # 데이터베이스에 기록
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO nonce_history (nonce, used_at) VALUES (?, ?)",
                    (nonce, datetime.now())
                )
                conn.commit()

        except Exception as e:
            self.logger.error(f"Nonce 기록 실패: {e}")

    def validate_nonce_format(self, nonce: str) -> bool:
        """Nonce 형식 검증"""
        try:
            # 길이 확인 (타임스탬프 16자리 + 랜덤 8자리 = 24자리)
            if len(nonce) != 24:
                return False

            # 숫자/16진수 확인
            timestamp_part = nonce[:16]
            random_part = nonce[16:]

            # 타임스탬프 부분은 숫자여야 함
            int(timestamp_part)

            # 랜덤 부분은 16진수여야 함
            int(random_part, 16)

            # 시간 범위 확인 (현재 시간 ±10분)
            timestamp = int(timestamp_part) / 1000000
            current_time = self.get_synchronized_timestamp()
            time_diff = abs(timestamp - current_time)

            if time_diff > 600:  # 10분 초과
                self.logger.warning(f"Nonce 시간 범위 초과: {time_diff:.2f}초")
                return False

            return True

        except ValueError:
            return False

    def cleanup_old_nonces(self):
        """오래된 Nonce 기록 정리"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                deleted = conn.execute('''
                    DELETE FROM nonce_history
                    WHERE created_at < datetime('now', '-7 days')
                ''').rowcount
                conn.commit()

                if deleted > 0:
                    self.logger.info(f"오래된 Nonce 기록 {deleted}개 삭제됨")

        except Exception as e:
            self.logger.error(f"Nonce 정리 실패: {e}")

    def get_nonce_stats(self) -> dict:
        """Nonce 사용 통계"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN created_at >= datetime('now', '-1 hour') THEN 1 END) as last_hour,
                        COUNT(CASE WHEN created_at >= datetime('now', '-1 day') THEN 1 END) as last_day
                    FROM nonce_history
                ''')
                row = cursor.fetchone()

                return {
                    'total_nonces': row[0],
                    'last_hour': row[1],
                    'last_day': row[2],
                    'memory_cache_size': len(self.used_nonces),
                    'time_offset': self.time_offset
                }

        except Exception as e:
            self.logger.error(f"Nonce 통계 조회 실패: {e}")
            return {}