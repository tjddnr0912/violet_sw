#!/usr/bin/env python3
"""
API 보안 모니터링 및 위험 감지 시스템
"""

import logging
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import threading
import smtplib
from email.mime.text import MIMEText
import os

@dataclass
class SecurityEvent:
    timestamp: datetime
    event_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    details: Dict[str, Any]
    resolved: bool = False

class SecurityMonitor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.failed_attempts = defaultdict(int)
        self.security_events: List[SecurityEvent] = []
        self.rate_limits = defaultdict(deque)  # API 호출 빈도 추적
        self.suspicious_patterns = []
        self.emergency_stop = False
        self.lock = threading.Lock()

        # 설정
        self.max_failed_attempts = 5
        self.lockdown_duration = 300  # 5분
        self.rate_limit_window = 60   # 1분
        self.max_requests_per_minute = 20

    def check_api_response(self, endpoint: str, response_data: Dict, request_data: Dict = None) -> bool:
        """API 응답 보안 검증"""
        with self.lock:
            status = response_data.get('status', 'unknown')

            # 성공 응답 처리
            if status == '0000':
                self._reset_failed_attempts(endpoint)
                return True

            # 보안 관련 오류 처리
            security_errors = {
                '5100': 'CRITICAL',  # 잘못된 API 키
                '5200': 'HIGH',      # API 서명 오류
                '5300': 'HIGH',      # Nonce 값 오류
                '5600': 'HIGH',      # API 권한 없음
                '5400': 'MEDIUM',    # HTTP Method 오류
                '5500': 'MEDIUM'     # 요청 시간 초과
            }

            if status in security_errors:
                severity = security_errors[status]
                self._record_security_event(endpoint, status, severity, response_data, request_data)
                self._increment_failed_attempts(endpoint, status)

                # 임계치 초과 시 보안 조치
                if self.failed_attempts[f"{endpoint}_{status}"] >= self.max_failed_attempts:
                    self._trigger_security_lockdown(endpoint, status, severity)
                    return False

            return False

    def check_rate_limit(self, endpoint: str) -> bool:
        """API 호출 빈도 제한 확인"""
        with self.lock:
            current_time = time.time()
            rate_queue = self.rate_limits[endpoint]

            # 1분 이전 요청 제거
            while rate_queue and rate_queue[0] < current_time - self.rate_limit_window:
                rate_queue.popleft()

            # 요청 빈도 확인
            if len(rate_queue) >= self.max_requests_per_minute:
                self._record_security_event(
                    endpoint, 'RATE_LIMIT_EXCEEDED', 'MEDIUM',
                    {'requests_per_minute': len(rate_queue)}
                )
                return False

            # 현재 요청 기록
            rate_queue.append(current_time)
            return True

    def detect_suspicious_patterns(self, endpoint: str, parameters: Dict) -> bool:
        """의심스러운 거래 패턴 감지"""
        try:
            # 거래 관련 엔드포인트만 검사
            if '/trade/' not in endpoint:
                return True

            # 1. 비정상적으로 큰 거래량
            if 'units' in parameters:
                units = float(parameters['units'])
                if units > 10.0:  # 임계값: 10코인
                    self._record_security_event(
                        endpoint, 'LARGE_TRADE_ATTEMPT', 'HIGH',
                        {'units': units, 'threshold': 10.0}
                    )
                    return False

            # 2. 비정상적으로 큰 거래금액
            if 'total' in parameters:
                total = float(parameters['total'])
                if total > 10000000:  # 임계값: 1000만원
                    self._record_security_event(
                        endpoint, 'LARGE_AMOUNT_ATTEMPT', 'HIGH',
                        {'total': total, 'threshold': 10000000}
                    )
                    return False

            # 3. 연속된 동일 거래 시도
            recent_requests = self._get_recent_requests(endpoint, 60)  # 1분 내
            if len(recent_requests) > 5:  # 1분에 5회 이상
                self._record_security_event(
                    endpoint, 'RAPID_TRADING_PATTERN', 'MEDIUM',
                    {'requests_count': len(recent_requests)}
                )
                return False

            return True

        except Exception as e:
            self.logger.error(f"패턴 감지 중 오류: {e}")
            return True  # 안전을 위해 허용

    def _record_security_event(self, endpoint: str, event_type: str, severity: str,
                              response_data: Dict = None, request_data: Dict = None):
        """보안 이벤트 기록"""
        event = SecurityEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            severity=severity,
            details={
                'endpoint': endpoint,
                'response': self._sanitize_data(response_data) if response_data else None,
                'request': self._sanitize_data(request_data) if request_data else None
            }
        )

        self.security_events.append(event)

        # 이벤트 로깅
        self.logger.warning(f"보안 이벤트: {event_type} ({severity}) - {endpoint}")

        # 심각한 이벤트는 즉시 알림
        if severity in ['HIGH', 'CRITICAL']:
            self._send_security_alert(event)

        # 오래된 이벤트 정리 (최근 24시간만 유지)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.security_events = [e for e in self.security_events if e.timestamp > cutoff_time]

    def _increment_failed_attempts(self, endpoint: str, error_code: str):
        """실패 횟수 증가"""
        key = f"{endpoint}_{error_code}"
        self.failed_attempts[key] += 1
        self.logger.info(f"실패 횟수 증가: {key} = {self.failed_attempts[key]}")

    def _reset_failed_attempts(self, endpoint: str):
        """성공 시 실패 횟수 초기화"""
        keys_to_reset = [key for key in self.failed_attempts.keys() if key.startswith(endpoint)]
        for key in keys_to_reset:
            self.failed_attempts[key] = 0

    def _trigger_security_lockdown(self, endpoint: str, error_code: str, severity: str):
        """보안 위험 시 긴급 조치"""
        self.emergency_stop = True

        lockdown_event = SecurityEvent(
            timestamp=datetime.now(),
            event_type='SECURITY_LOCKDOWN',
            severity='CRITICAL',
            details={
                'endpoint': endpoint,
                'error_code': error_code,
                'trigger_severity': severity,
                'failed_attempts': self.failed_attempts[f"{endpoint}_{error_code}"]
            }
        )

        self.security_events.append(lockdown_event)
        self.logger.critical(f"보안 잠금 활성화: {endpoint} - {error_code}")

        # 긴급 알림 발송
        self._send_emergency_alert(lockdown_event)

        # 자동 해제 스케줄링
        threading.Timer(self.lockdown_duration, self._release_lockdown).start()

    def _release_lockdown(self):
        """보안 잠금 해제"""
        self.emergency_stop = False
        self.failed_attempts.clear()
        self.logger.info("보안 잠금이 해제되었습니다.")

    def _sanitize_data(self, data: Dict) -> Dict:
        """민감한 데이터 마스킹"""
        if not data:
            return {}

        sanitized = data.copy()
        sensitive_fields = ['api_key', 'signature', 'nonce', 'units', 'total', 'balance']

        for field in sensitive_fields:
            if field in sanitized:
                if isinstance(sanitized[field], str):
                    sanitized[field] = f"{sanitized[field][:4]}****{sanitized[field][-4:]}"
                elif isinstance(sanitized[field], (int, float)):
                    sanitized[field] = "***MASKED***"

        return sanitized

    def _get_recent_requests(self, endpoint: str, seconds: int) -> List[float]:
        """최근 요청 기록 조회"""
        current_time = time.time()
        rate_queue = self.rate_limits[endpoint]
        return [req_time for req_time in rate_queue if req_time > current_time - seconds]

    def _send_security_alert(self, event: SecurityEvent):
        """보안 알림 발송"""
        try:
            # 이메일 알림 (환경변수에서 설정 로드)
            alert_email = os.getenv('SECURITY_ALERT_EMAIL')
            smtp_server = os.getenv('SMTP_SERVER', 'localhost')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))

            if alert_email:
                subject = f"[보안 알림] {event.event_type} - {event.severity}"
                body = f"""
보안 이벤트가 발생했습니다.

시간: {event.timestamp}
유형: {event.event_type}
심각도: {event.severity}
세부사항: {json.dumps(event.details, indent=2, ensure_ascii=False)}

즉시 확인이 필요합니다.
"""

                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = 'security@tradingbot.local'
                msg['To'] = alert_email

                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.send_message(msg)

                self.logger.info(f"보안 알림 발송 완료: {alert_email}")

        except Exception as e:
            self.logger.error(f"보안 알림 발송 실패: {e}")

    def _send_emergency_alert(self, event: SecurityEvent):
        """긴급 알림 발송"""
        self.logger.critical("=== 긴급 보안 알림 ===")
        self.logger.critical(f"시간: {event.timestamp}")
        self.logger.critical(f"이벤트: {event.event_type}")
        self.logger.critical(f"세부사항: {event.details}")
        self.logger.critical("모든 거래가 중단되었습니다.")

        # 추가 알림 채널 (슬랙, 텔레그램 등) 구현 가능

    def get_security_status(self) -> Dict[str, Any]:
        """보안 상태 요약"""
        recent_events = [e for e in self.security_events
                        if e.timestamp > datetime.now() - timedelta(hours=1)]

        return {
            'emergency_stop': self.emergency_stop,
            'total_events_24h': len(self.security_events),
            'recent_events_1h': len(recent_events),
            'failed_attempts': dict(self.failed_attempts),
            'rate_limits': {endpoint: len(queue) for endpoint, queue in self.rate_limits.items()},
            'high_severity_events': len([e for e in recent_events if e.severity in ['HIGH', 'CRITICAL']]),
            'last_event': self.security_events[-1].event_type if self.security_events else None
        }

    def reset_security_state(self, confirm_token: str):
        """보안 상태 초기화 (관리자 전용)"""
        expected_token = os.getenv('SECURITY_RESET_TOKEN', 'default_token')

        if confirm_token != expected_token:
            self.logger.warning("보안 상태 초기화 시도 실패: 잘못된 토큰")
            return False

        self.emergency_stop = False
        self.failed_attempts.clear()
        self.rate_limits.clear()
        self.security_events.clear()

        self.logger.info("보안 상태가 수동으로 초기화되었습니다.")
        return True