"""ChannelMasteryAnalyzer - 채널 데이터 기반 전문가 컨텍스트 생성"""

import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# 3중 import fallback
try:
    from scripts.knowledge.store import KnowledgeStore
    from scripts.knowledge.channel_profile import ChannelProfileStore
except ImportError:
    try:
        from knowledge.store import KnowledgeStore
        from knowledge.channel_profile import ChannelProfileStore
    except ImportError:
        from .store import KnowledgeStore
        from .channel_profile import ChannelProfileStore


# 한국어 불용어 (조사, 접속사, 1음절 한자어 등)
KOREAN_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "에", "의", "로", "로서", "으로",
    "와", "과", "에서", "까지", "부터", "도", "만", "조차", "밖에",
    "그", "저", "이것", "그것", "저것", "이런", "그런", "저런",
    "하다", "되다", "있다", "없다", "않다", "같다", "나다",
    "그리고", "하지만", "그러나", "또는", "혹은", "및", "그래서",
    "네", "예", "아니요", "안녕", "감사", "수고",
    "좀", "더", "매우", "아주", "너무", "정말", "진짜",
    "것", "수", "등", "중", "때", "후", "전", "위", "아래",
}

# 영어 불용어
ENGLISH_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "must", "need",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "and", "or", "but", "if", "then", "else", "when", "where", "how",
    "not", "no", "nor", "only", "just", "also", "very", "too",
    "in", "on", "at", "to", "for", "with", "from", "by", "of", "about",
    "up", "out", "so", "as", "all", "any", "each", "every",
}

# 의사결정 패턴 (한국어)
DECISION_PATTERNS = [
    r"결정|확정|채택|승인|반려",
    r"진행하기로|하기로\s*했|로\s*결정",
    r"완료[했됐]|마무리[했됐]",
    r"확인[했됐]|합의[했됐]",
]

# 액션 키워드 (실행 담당자 식별용)
ACTION_KEYWORDS = {"배포", "릴리즈", "머지", "deploy", "release", "merge", "push", "commit", "PR"}

# 요청자 패턴
REQUEST_PATTERNS = [r"\?", r"부탁", r"해주세요", r"해줘", r"확인.*부탁", r"검토.*부탁"]


class ChannelMasteryAnalyzer:
    """채널 데이터 기반 전문가 컨텍스트 생성

    Knowledge Store에 축적된 채널 메시지 전체를 분석하여
    AI가 즉시 활용 가능한 전문가 요약을 생성합니다.
    """

    def __init__(self, store: KnowledgeStore, profile_store: ChannelProfileStore):
        self.store = store
        self.profile_store = profile_store

    async def build_mastery_context(
        self,
        project_id: str,
        channel_id: str,
        top_n_keywords: int = 20,
    ) -> dict:
        """채널 전문가 컨텍스트 생성

        Returns:
            {
                "channel_summary": "채널 목적 + 주요 활동 요약",
                "top_keywords": ["배포", "일정", "리뷰", ...],
                "key_decisions": ["2026-02-10: A 방식으로 구현 결정", ...],
                "member_roles": {"U040EUZ6JRY": "주요 의사결정권자", ...},
                "active_topics": ["gateway 개발", "intelligence 개선", ...],
            }
        """
        try:
            # 전체 메시지 로드
            documents = await self.store.get_recent(
                project_id=project_id,
                limit=5000,
                source="slack",
            )
        except Exception:
            logger.exception("get_recent 실패")
            documents = []

        if not documents:
            return {
                "channel_summary": "",
                "top_keywords": [],
                "key_decisions": [],
                "member_roles": {},
                "active_topics": [],
            }

        # 채널 프로파일
        try:
            profile = await self.profile_store.get(channel_id)
        except Exception:
            logger.exception("profile_store.get 실패")
            profile = None

        # 1. 상위 키워드 추출 (TF-IDF)
        top_keywords = self._extract_keywords(documents, top_n_keywords)

        # 2. 의사결정 추출
        key_decisions = self._extract_decisions(documents)

        # 3. 멤버 역할 파악
        member_roles = self._analyze_member_roles(documents)

        # 4. 활성 토픽 추출 (최근 30일)
        active_topics = self._extract_active_topics(documents, top_keywords)

        # 5. 채널 요약 생성
        channel_summary = self._build_summary(profile, documents, top_keywords)

        return {
            "channel_summary": channel_summary,
            "top_keywords": top_keywords,
            "key_decisions": key_decisions[:10],
            "member_roles": member_roles,
            "active_topics": active_topics[:10],
        }

    def _tokenize(self, text: str) -> List[str]:
        """텍스트를 토큰화 (한국어 + 영어)"""
        if not text:
            return []
        # 공백/구두점 분리, 2자 이상만
        tokens = re.findall(r'[가-힣]{2,}|[a-zA-Z]{2,}|[0-9]+[a-zA-Z]+|[a-zA-Z]+[0-9]+', text)
        return [t.lower() for t in tokens]

    def _extract_keywords(self, documents: list, top_n: int = 20) -> List[str]:
        """TF-IDF 간이 구현으로 상위 키워드 추출"""
        if not documents:
            return []

        try:
            all_stopwords = KOREAN_STOPWORDS | ENGLISH_STOPWORDS

            # 각 문서의 토큰화
            doc_tokens = []
            for doc in documents:
                tokens = self._tokenize(doc.content)
                filtered = [t for t in tokens if t not in all_stopwords and len(t) >= 2]
                doc_tokens.append(filtered)

            # TF 계산 (전체 합산)
            tf_counter = Counter()
            for tokens in doc_tokens:
                tf_counter.update(tokens)

            # DF 계산 (각 단어가 몇 개 문서에 출현)
            df_counter = Counter()
            for tokens in doc_tokens:
                unique_tokens = set(tokens)
                df_counter.update(unique_tokens)

            # TF-IDF 점수
            num_docs = len(documents)
            tfidf_scores = {}
            for word, tf in tf_counter.items():
                df = df_counter.get(word, 1)
                idf = math.log(num_docs / df) if df > 0 else 0
                tfidf_scores[word] = tf * idf

            # 상위 N개 반환
            sorted_keywords = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)
            return [word for word, score in sorted_keywords[:top_n]]
        except Exception:
            logger.exception("_extract_keywords 실패")
            return []

    def _extract_decisions(self, documents: list) -> List[str]:
        """의사결정 관련 메시지 추출"""
        decisions = []

        try:
            compiled_patterns = [re.compile(p) for p in DECISION_PATTERNS]

            for doc in documents:
                text = doc.content
                if not text:
                    continue

                # 의사결정 패턴 매칭
                matched = any(p.search(text) for p in compiled_patterns)
                if not matched:
                    continue

                # 날짜 포맷
                date_str = ""
                if doc.created_at:
                    date_str = doc.created_at.strftime("%Y-%m-%d")

                # 문장 단위로 관련 부분 추출
                sentences = re.split(r'[.!?\n]', text)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence or len(sentence) < 5:
                        continue
                    if any(p.search(sentence) for p in compiled_patterns):
                        # 최대 200자
                        truncated = sentence[:200]
                        if date_str:
                            decisions.append(f"{date_str}: {truncated}")
                        else:
                            decisions.append(truncated)
                        break
        except Exception:
            logger.exception("_extract_decisions 실패")

        return decisions

    def _analyze_member_roles(self, documents: list) -> Dict[str, str]:
        """멤버 역할 분류 (발언량, 액션, 요청 패턴 기반)"""
        if not documents:
            return {}

        try:
            # 멤버별 통계
            msg_count = Counter()  # 발언량
            action_count = Counter()  # 액션 키워드 발언
            request_count = Counter()  # 요청 패턴 발언

            compiled_request = [re.compile(p) for p in REQUEST_PATTERNS]

            for doc in documents:
                sender = doc.sender_name or doc.sender_id
                if not sender:
                    continue

                msg_count[sender] += 1

                text = (doc.content or "").lower()

                # 액션 키워드 체크
                for keyword in ACTION_KEYWORDS:
                    if keyword.lower() in text:
                        action_count[sender] += 1
                        break

                # 요청 패턴 체크
                for pattern in compiled_request:
                    if pattern.search(doc.content or ""):
                        request_count[sender] += 1
                        break

            if not msg_count:
                return {}

            roles = {}

            # 상위 3인: 주요 발언자
            top_speakers = msg_count.most_common(3)
            for sender, count in top_speakers:
                roles[sender] = "주요 발언자"

            # 액션 키워드 비율 높은 멤버: 실행 담당
            for sender, a_count in action_count.most_common():
                sender_total = msg_count.get(sender, 1)
                if sender_total > 0 and (a_count / sender_total) > 0.15:
                    roles[sender] = "실행 담당"

            # 요청 패턴 비율 높은 멤버: 요청자
            for sender, r_count in request_count.most_common():
                sender_total = msg_count.get(sender, 1)
                if sender_total > 0 and (r_count / sender_total) > 0.2:
                    if sender not in roles or roles[sender] == "주요 발언자":
                        roles[sender] = "요청자"

            return roles
        except Exception:
            logger.exception("_analyze_member_roles 실패")
            return {}

    def _extract_active_topics(self, documents: list, keywords: List[str]) -> List[str]:
        """최근 30일 메시지에서 활성 토픽 추출"""
        try:
            cutoff = datetime.now() - timedelta(days=30)
            recent_docs = [d for d in documents if d.created_at and d.created_at >= cutoff]

            if not recent_docs:
                return keywords[:5] if keywords else []

            # 최근 문서에서 키워드 빈도 재계산
            recent_counter = Counter()
            for doc in recent_docs:
                tokens = self._tokenize(doc.content)
                keyword_set = set(keywords[:50])
                for t in tokens:
                    if t in keyword_set:
                        recent_counter[t] += 1

            # 공출현 기반 클러스터링 (단순 접근)
            # 같은 메시지에 동시 출현하는 키워드 쌍 → 토픽
            co_occurrence = defaultdict(int)
            for doc in recent_docs:
                tokens = set(self._tokenize(doc.content))
                keyword_tokens = tokens & set(keywords[:30])
                kw_list = sorted(keyword_tokens)
                for i in range(len(kw_list)):
                    for j in range(i + 1, len(kw_list)):
                        pair = f"{kw_list[i]} {kw_list[j]}"
                        co_occurrence[pair] += 1

            # 토픽: 공출현 빈도 상위 + 단독 키워드
            topics = []
            sorted_pairs = sorted(co_occurrence.items(), key=lambda x: x[1], reverse=True)
            for pair, count in sorted_pairs[:5]:
                if count >= 2:
                    topics.append(pair)

            # 단독 키워드도 추가
            for kw, count in recent_counter.most_common(10):
                if kw not in " ".join(topics) and len(topics) < 10:
                    topics.append(kw)

            return topics
        except Exception:
            logger.exception("_extract_active_topics 실패")
            return keywords[:5] if keywords else []

    def _build_summary(self, profile, documents: list, keywords: List[str]) -> str:
        """채널 요약 생성"""
        try:
            parts = []

            if profile:
                if profile.channel_name:
                    parts.append(f"#{profile.channel_name}")
                if profile.purpose:
                    parts.append(f"목적: {profile.purpose}")
                if profile.topic:
                    parts.append(f"토픽: {profile.topic}")
                if profile.members:
                    parts.append(f"멤버 {len(profile.members)}명")

            parts.append(f"메시지 {len(documents)}건 분석")

            if keywords:
                parts.append(f"주요 키워드: {', '.join(keywords[:5])}")

            return " | ".join(parts)
        except Exception:
            logger.exception("_build_summary 실패")
            return f"메시지 {len(documents)}건 분석"
