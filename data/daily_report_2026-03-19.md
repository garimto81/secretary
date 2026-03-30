*일일 브리핑* — 2026-03-19 (수요일)

*어제까지*
• Secretary: /daily 3시제 재설계 완료 — projects.json 52개 레포 매핑, SKILL.md v5.0 전환
• EBS: PokerGFX 역공학 분석 진행 중 — annotation 파이프라인 기술 스택 확정
• Infra: Claude Code 워크플로우 v23.0 구조 경량화 완료

*오늘 한 일* (커밋 7건 / +11,815 -5,911)

_회의 자동화 — STT 엔진 선정_
• SenseVoice STT + Qwen 요약 POC 검증 (4종 시뮬레이션)
• Whisper 한국어 비교 POC → STT 엔진 최종 선정
• POC 검증 결과 PRD 반영 (SenseVoice 정확도 이슈, Qwen 요약 채택)

_워크플로우 개선_
• Progressive Disclosure v25.2 — SKILL.md 분업화 + Phase별 reference 분리
• 스킬 감사 — YAML 파서 교체 + 9개 SKILL.md description 개선

_WSOP Academy 홈페이지_
• v11.0 제품 소개 재설계 — "Poker is fun." 컨셉
• 이모지 아이콘 제거 + LearningPath 곡선 경로 + bento 카드 시각 요소

*파일시스템 변경* (git 미추적 포함)
• ebs_ui: +9 ~2 파일 | game_kfc: ~3 파일 | secretary: ~1 파일

*프로젝트 현황*
• EBS 62% | Secretary 81% | GitHub 이슈 30건 오픈

*앞으로 대비*
• STT 엔진 최종 선정 → 회의 자동화 파이프라인 본격 구현
• WSOP Academy v11.0 QA 및 배포
• :warning: #140 Agent Teams 종료 실패 — 26일 미해결
• :warning: #141 annotation consensus — 16일 미해결