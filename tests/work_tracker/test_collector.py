"""
GitCollector 단위 테스트

실제 git 명령 실행 없이 mock/fixture 기반으로 검증한다.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.collector import GitCollector
from scripts.work_tracker.models import CommitType, DailyCommit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector(tmp_path):
    """최소 설정의 GitCollector (빈 repo mapping)"""
    config = tmp_path / "projects.json"
    config.write_text(
        json.dumps(
            {
                "local_repo_mapping": {
                    "ebs": {"project": "EBS", "category": "기획"},
                    "secretary": {"project": "Secretary", "category": "자동화"},
                }
            }
        ),
        encoding="utf-8",
    )
    return GitCollector(base_dir=str(tmp_path), config_path=config)


@pytest.fixture
def collector_no_config(tmp_path):
    """존재하지 않는 config 경로 → fallback empty mapping"""
    return GitCollector(
        base_dir=str(tmp_path),
        config_path=tmp_path / "nonexistent.json",
    )


# ---------------------------------------------------------------------------
# _load_repo_mapping
# ---------------------------------------------------------------------------


class TestLoadRepoMapping:
    def test_loads_mapping_from_valid_config(self, collector):
        mapping = collector._repo_mapping
        assert "ebs" in mapping
        assert mapping["ebs"]["project"] == "EBS"

    def test_returns_empty_dict_on_missing_file(self, collector_no_config):
        assert collector_no_config._repo_mapping == {}

    def test_returns_empty_dict_on_invalid_json(self, tmp_path):
        config = tmp_path / "bad.json"
        config.write_text("not valid json", encoding="utf-8")
        gc = GitCollector(base_dir=str(tmp_path), config_path=config)
        assert gc._repo_mapping == {}

    def test_returns_empty_dict_when_key_missing(self, tmp_path):
        config = tmp_path / "projects.json"
        config.write_text(json.dumps({"projects": []}), encoding="utf-8")
        gc = GitCollector(base_dir=str(tmp_path), config_path=config)
        assert gc._repo_mapping == {}


# ---------------------------------------------------------------------------
# discover_repos
# ---------------------------------------------------------------------------


class TestDiscoverRepos:
    def test_finds_repos_with_git_dir(self, collector, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        (repo_a / ".git").mkdir()

        repo_b = tmp_path / "repo_b"
        repo_b.mkdir()
        (repo_b / ".git").mkdir()

        # no .git
        no_git = tmp_path / "no_git"
        no_git.mkdir()

        repos = collector.discover_repos()
        repo_names = {r.name for r in repos}
        assert "repo_a" in repo_names
        assert "repo_b" in repo_names
        assert "no_git" not in repo_names

    def test_returns_empty_when_no_repos(self, collector):
        repos = collector.discover_repos()
        assert repos == []

    def test_does_not_recurse_into_subdirectories(self, collector, tmp_path):
        """재귀 탐색 금지: 손자 디렉토리의 .git은 포함하지 않는다"""
        nested = tmp_path / "parent" / "child"
        nested.mkdir(parents=True)
        (nested / ".git").mkdir()

        repos = collector.discover_repos()
        assert repos == []


# ---------------------------------------------------------------------------
# _parse_conventional_commit
# ---------------------------------------------------------------------------


class TestParseConventionalCommit:
    @pytest.mark.parametrize(
        "message, expected_type, expected_scope, expected_desc",
        [
            # 기본 타입
            ("feat: add login", CommitType.FEAT, None, "add login"),
            ("fix: resolve null pointer", CommitType.FIX, None, "resolve null pointer"),
            ("docs: update readme", CommitType.DOCS, None, "update readme"),
            ("refactor: extract helper", CommitType.REFACTOR, None, "extract helper"),
            ("test: add unit tests", CommitType.TEST, None, "add unit tests"),
            ("chore: bump version", CommitType.CHORE, None, "bump version"),
            ("style: fix formatting", CommitType.STYLE, None, "fix formatting"),
            ("perf: optimize query", CommitType.PERF, None, "optimize query"),
            ("ci: update pipeline", CommitType.CI, None, "update pipeline"),
            ("build: upgrade deps", CommitType.BUILD, None, "upgrade deps"),
            # scope 있음
            ("feat(ui): add button", CommitType.FEAT, "ui", "add button"),
            ("fix(auth): token expiry", CommitType.FIX, "auth", "token expiry"),
            ("docs(api): add endpoint docs", CommitType.DOCS, "api", "add endpoint docs"),
            # breaking change (!) — scope 없음
            ("feat!: breaking change", CommitType.FEAT, None, "breaking change"),
            # breaking change (!) — scope 있음
            ("feat(core)!: drop python 3.8", CommitType.FEAT, "core", "drop python 3.8"),
            # 알 수 없는 타입 → OTHER (scope는 그대로 추출됨)
            ("unknown: something", CommitType.OTHER, None, "something"),
            ("xyz(scope): desc", CommitType.OTHER, "scope", "desc"),
            # 매칭 실패
            ("just a plain message", CommitType.OTHER, None, "just a plain message"),
            ("", CommitType.OTHER, None, ""),
            ("WIP: work in progress", CommitType.OTHER, None, "work in progress"),
        ],
    )
    def test_parse(self, collector, message, expected_type, expected_scope, expected_desc):
        commit_type, scope, desc = collector._parse_conventional_commit(message)
        assert commit_type == expected_type
        assert scope == expected_scope
        assert desc == expected_desc

    def test_description_stripped(self, collector):
        _, _, desc = collector._parse_conventional_commit("feat:   leading spaces  ")
        assert desc == "leading spaces"

    def test_multiword_scope(self, collector):
        _, scope, _ = collector._parse_conventional_commit("feat(work-tracker): add collector")
        assert scope == "work-tracker"


# ---------------------------------------------------------------------------
# _classify_repo
# ---------------------------------------------------------------------------


class TestClassifyRepo:
    def test_mapped_repo_returns_project_and_category(self, collector):
        project, category = collector._classify_repo("ebs")
        assert project == "EBS"
        assert category == "기획"

    def test_another_mapped_repo(self, collector):
        project, category = collector._classify_repo("secretary")
        assert project == "Secretary"
        assert category == "자동화"

    def test_unmapped_repo_returns_기타(self, collector):
        project, category = collector._classify_repo("unknown_repo")
        assert project == "기타"
        assert category is None

    def test_empty_string_returns_기타(self, collector):
        project, category = collector._classify_repo("")
        assert project == "기타"
        assert category is None


# ---------------------------------------------------------------------------
# _extract_branch
# ---------------------------------------------------------------------------


class TestExtractBranch:
    def test_head_arrow_branch(self, collector):
        branch = collector._extract_branch("HEAD -> main, origin/main")
        assert branch == "main"

    def test_head_arrow_feature_branch(self, collector):
        branch = collector._extract_branch("HEAD -> feat/anno-workflow")
        assert branch == "feat/anno-workflow"

    def test_origin_branch(self, collector):
        branch = collector._extract_branch("origin/develop")
        assert branch == "develop"

    def test_empty_ref_names(self, collector):
        assert collector._extract_branch("") is None
        assert collector._extract_branch("   ") is None

    def test_first_ref_fallback(self, collector):
        branch = collector._extract_branch("tag-v1.0.0, upstream/main")
        assert branch == "tag-v1.0.0"


# ---------------------------------------------------------------------------
# _parse_file_changes
# ---------------------------------------------------------------------------


class TestParseFileChanges:
    def test_normal_stat_output(self, collector):
        lines = [
            " scripts/collector.py | 50 +++++++++++++++++++++-----------------------------",
            " tests/test_collector.py | 30 ++++++++++++++++++",
            " 2 files changed, 30 insertions(+), 20 deletions(-)",
        ]
        files_changed, ins, dels, file_changes = collector._parse_file_changes(lines)
        assert files_changed == 2
        assert ins == 30
        assert dels == 20
        assert len(file_changes) == 2

    def test_insertions_only(self, collector):
        lines = [
            " new_file.py | 10 ++++++++++",
            " 1 file changed, 10 insertions(+)",
        ]
        files_changed, ins, dels, _ = collector._parse_file_changes(lines)
        assert files_changed == 1
        assert ins == 10
        assert dels == 0

    def test_deletions_only(self, collector):
        lines = [
            " old_file.py | 5 -----",
            " 1 file changed, 5 deletions(-)",
        ]
        files_changed, ins, dels, _ = collector._parse_file_changes(lines)
        assert files_changed == 1
        assert ins == 0
        assert dels == 5

    def test_binary_file(self, collector):
        lines = [
            " image.png | Bin 0 -> 1024 bytes",
            " 1 file changed",
        ]
        _, _, _, file_changes = collector._parse_file_changes(lines)
        assert len(file_changes) == 1
        assert file_changes[0].change_type == "modified"
        assert file_changes[0].insertions == 0

    def test_file_change_types(self, collector):
        lines = [
            " added.py | 5 +++++",
            " deleted.py | 3 ---",
            " modified.py | 4 ++--",
            " 3 files changed, 7 insertions(+), 5 deletions(-)",
        ]
        _, _, _, file_changes = collector._parse_file_changes(lines)
        types = {fc.file_path: fc.change_type for fc in file_changes}
        assert types["added.py"] == "added"
        assert types["deleted.py"] == "deleted"
        assert types["modified.py"] == "modified"

    def test_empty_stat_lines(self, collector):
        files_changed, ins, dels, file_changes = collector._parse_file_changes([])
        assert files_changed == 0
        assert ins == 0
        assert dels == 0
        assert file_changes == []

    def test_summary_line_singular_file(self, collector):
        lines = [" 1 file changed, 1 insertion(+)"]
        files_changed, ins, dels, _ = collector._parse_file_changes(lines)
        assert files_changed == 1
        assert ins == 1
        assert dels == 0


# ---------------------------------------------------------------------------
# _parse_git_output
# ---------------------------------------------------------------------------


class TestParseGitOutput:
    # Realistic mock output from git log --format="%H|%s|%an|%ai|%D" --stat
    # Hashes are exactly 40 hex characters
    MOCK_GIT_OUTPUT = """\
abc1234567890abcdef1234567890abcdef12345|feat(ui): add login button|Alice|2026-03-17 10:00:00 +0900|HEAD -> feat/login, origin/feat/login
 src/ui/button.py | 20 ++++++++++++++++++++
 tests/test_button.py | 15 +++++++++++++++
 2 files changed, 35 insertions(+)

def4567890abcdef1234567890abcdef1234567|fix: resolve crash on startup|Bob|2026-03-17 11:30:00 +0900|
 src/main.py | 5 ++---
 1 file changed, 3 insertions(+), 2 deletions(-)

"""

    def test_parses_two_commits(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "ebs", "2026-03-17"
        )
        assert len(commits) == 2

    def test_first_commit_fields(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "ebs", "2026-03-17"
        )
        c = commits[0]
        assert c.commit_hash == "abc1234567890abcdef1234567890abcdef12345"
        assert c.commit_type == CommitType.FEAT
        assert c.commit_scope == "ui"
        assert c.message == "add login button"
        assert c.author == "Alice"
        assert c.branch == "feat/login"
        assert c.files_changed == 2
        assert c.insertions == 35
        assert c.deletions == 0

    def test_second_commit_fields(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "ebs", "2026-03-17"
        )
        c = commits[1]
        assert c.commit_type == CommitType.FIX
        assert c.commit_scope is None
        assert c.message == "resolve crash on startup"
        assert c.author == "Bob"
        assert c.files_changed == 1
        assert c.insertions == 3
        assert c.deletions == 2

    def test_repo_classification_applied(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "ebs", "2026-03-17"
        )
        for c in commits:
            assert c.project == "EBS"
            assert c.category == "기획"

    def test_unmapped_repo_gets_기타(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "unknown_repo", "2026-03-17"
        )
        for c in commits:
            assert c.project == "기타"
            assert c.category is None

    def test_empty_output_returns_empty_list(self, collector):
        assert collector._parse_git_output("", "ebs", "2026-03-17") == []
        assert collector._parse_git_output("   \n\n", "ebs", "2026-03-17") == []

    def test_date_field_set_correctly(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "ebs", "2026-03-17"
        )
        assert all(c.date == "2026-03-17" for c in commits)

    def test_repo_field_set_correctly(self, collector):
        commits = collector._parse_git_output(
            self.MOCK_GIT_OUTPUT, "secretary", "2026-03-17"
        )
        assert all(c.repo == "secretary" for c in commits)


# ---------------------------------------------------------------------------
# collect_date (subprocess mock)
# ---------------------------------------------------------------------------


class TestCollectDate:
    MOCK_OUTPUT = """\
aabbccdd1234567890abcdef1234567890abcd01|docs: update readme|Dev|2026-03-17 09:00:00 +0900|HEAD -> main
 README.md | 3 +++
 1 file changed, 3 insertions(+)

"""

    def _make_mock_result(self, stdout="", returncode=0):
        mock = MagicMock()
        mock.stdout = stdout
        mock.returncode = returncode
        return mock

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_collects_from_provided_repos(self, mock_run, collector, tmp_path):
        mock_run.return_value = self._make_mock_result(self.MOCK_OUTPUT)

        repo = tmp_path / "secretary"
        repo.mkdir()
        (repo / ".git").mkdir()

        commits = collector.collect_date("2026-03-17", repos=[repo])
        assert len(commits) == 1
        assert commits[0].commit_type == CommitType.DOCS

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_skips_repo_on_timeout(self, mock_run, collector, tmp_path):
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd="git", timeout=30)

        repo = tmp_path / "ebs"
        repo.mkdir()
        (repo / ".git").mkdir()

        # should not raise, returns empty
        commits = collector.collect_date("2026-03-17", repos=[repo])
        assert commits == []

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_skips_repo_on_generic_error(self, mock_run, collector, tmp_path):
        mock_run.side_effect = OSError("git not found")

        repo = tmp_path / "ebs"
        repo.mkdir()
        (repo / ".git").mkdir()

        commits = collector.collect_date("2026-03-17", repos=[repo])
        assert commits == []

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_multiple_repos_aggregated(self, mock_run, collector, tmp_path):
        mock_run.return_value = self._make_mock_result(self.MOCK_OUTPUT)

        repos = []
        for name in ["ebs", "secretary"]:
            r = tmp_path / name
            r.mkdir()
            (r / ".git").mkdir()
            repos.append(r)

        commits = collector.collect_date("2026-03-17", repos=repos)
        assert len(commits) == 2

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_empty_git_output_returns_empty(self, mock_run, collector, tmp_path):
        mock_run.return_value = self._make_mock_result("")

        repo = tmp_path / "ebs"
        repo.mkdir()
        (repo / ".git").mkdir()

        commits = collector.collect_date("2026-03-17", repos=[repo])
        assert commits == []

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_git_command_uses_correct_date_range(self, mock_run, collector, tmp_path):
        mock_run.return_value = self._make_mock_result("")

        repo = tmp_path / "ebs"
        repo.mkdir()
        (repo / ".git").mkdir()

        collector.collect_date("2026-03-17", repos=[repo])

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--since=2026-03-17T00:00:00" in cmd
        assert "--until=2026-03-17T23:59:59" in cmd
        assert "--stat" in cmd

    @patch("scripts.work_tracker.collector.subprocess.run")
    def test_none_repos_uses_discover(self, mock_run, collector, tmp_path):
        """repos=None이면 discover_repos()로 자동 탐색"""
        mock_run.return_value = self._make_mock_result("")

        # tmp_path에 .git 디렉토리가 없으면 discover_repos()는 빈 리스트 반환
        commits = collector.collect_date("2026-03-17", repos=None)
        assert commits == []
        # subprocess.run은 호출되지 않아야 함
        mock_run.assert_not_called()
