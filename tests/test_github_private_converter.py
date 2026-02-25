"""GitHub Private Converter 단위 테스트"""
from unittest.mock import MagicMock, patch

import pytest


class TestCheckToken:
    """check_token 함수 테스트"""

    def test_check_token_with_repo_scope(self):
        """repo scope 있을 때 has_repo_scope=True"""
        from scripts.github_private_converter import check_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-OAuth-Scopes": "repo, read:user, workflow"}
        mock_response.json.return_value = {"login": "garimto81"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = check_token("fake_token")

        assert result["login"] == "garimto81"
        assert result["has_repo_scope"] is True
        assert "repo" in result["scopes"]

    def test_check_token_without_repo_scope(self):
        """repo scope 없을 때 has_repo_scope=False"""
        from scripts.github_private_converter import check_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-OAuth-Scopes": "read:user, gist"}
        mock_response.json.return_value = {"login": "garimto81"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = check_token("fake_token")

        assert result["has_repo_scope"] is False

    def test_check_token_api_failure(self):
        """API 실패 시 SystemExit"""
        from scripts.github_private_converter import check_token

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            with pytest.raises(SystemExit):
                check_token("bad_token")


class TestListPublicRepos:
    """list_public_repos 함수 테스트"""

    def test_list_public_repos_single_page(self):
        """단일 페이지 결과"""
        from scripts.github_private_converter import list_public_repos

        mock_repos = [
            {"name": "claude", "full_name": "garimto81/claude",
             "private": False, "html_url": "https://github.com/garimto81/claude"},
            {"name": "test", "full_name": "garimto81/test",
             "private": False, "html_url": "https://github.com/garimto81/test"},
        ]

        responses = [
            MagicMock(status_code=200, json=MagicMock(return_value=mock_repos)),
            MagicMock(status_code=200, json=MagicMock(return_value=[])),  # 빈 페이지 → 종료
        ]

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = responses
            result = list_public_repos("fake_token")

        assert len(result) == 2
        assert result[0]["full_name"] == "garimto81/claude"
        assert result[1]["full_name"] == "garimto81/test"

    def test_list_public_repos_empty(self):
        """public 저장소 없을 때 빈 리스트"""
        from scripts.github_private_converter import list_public_repos

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = list_public_repos("fake_token")

        assert result == []

    def test_list_public_repos_api_failure(self):
        """API 실패 시 SystemExit"""
        from scripts.github_private_converter import list_public_repos

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            with pytest.raises(SystemExit):
                list_public_repos("fake_token")


class TestConvertToPrivate:
    """convert_to_private 함수 테스트"""

    def test_convert_success(self):
        """정상 전환 성공"""
        from scripts.github_private_converter import convert_to_private

        # list_public_repos mock
        mock_repos = [
            {"full_name": "garimto81/claude", "name": "claude",
             "private": False, "url": "https://github.com/garimto81/claude"}
        ]

        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 200

        with patch("scripts.github_private_converter.list_public_repos", return_value=mock_repos):
            with patch("httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.patch.return_value = mock_patch_response
                with patch("builtins.input", return_value="yes"):
                    result = convert_to_private("fake_token")

        assert result["success"] == 1
        assert result["failed"] == 0


class TestVerifyConversion:
    """verify_conversion 함수 테스트"""

    def test_verify_all_private(self):
        """모두 private 전환 완료"""
        from scripts.github_private_converter import verify_conversion

        with patch("scripts.github_private_converter.list_public_repos", return_value=[]):
            result = verify_conversion("fake_token")

        assert result is True

    def test_verify_some_remaining(self):
        """일부 public 저장소 남아있을 때"""
        from scripts.github_private_converter import verify_conversion

        remaining = [{"full_name": "garimto81/old-repo", "name": "old-repo",
                      "private": False, "url": "https://github.com/garimto81/old-repo"}]

        with patch("scripts.github_private_converter.list_public_repos", return_value=remaining):
            result = verify_conversion("fake_token")

        assert result is False
