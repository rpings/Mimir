# -*- coding: utf-8 -*-
"""Tests for DingTalk notification client."""

import os
import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.storages.dingtalk_client import DingTalkNotifier
from src.processors.base_processor import ProcessedEntry


@pytest.fixture
def sample_entry():
    """Sample ProcessedEntry for testing."""
    return ProcessedEntry(
        title="Test Article Title",
        link="https://example.com/article",
        summary="This is a test article summary with some content.",
        source_name="Test Source",
        source_type="blog",
        topics=["AI", "RAG"],
        priority="High",
    )


@pytest.fixture
def dingtalk_notifier():
    """DingTalk notifier instance with webhook URL."""
    return DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test")


def test_dingtalk_notifier_init_with_url():
    """Test DingTalk notifier initialization with URL."""
    notifier = DingTalkNotifier(webhook_url="https://test.com/webhook")
    assert notifier.webhook_url == "https://test.com/webhook"
    assert notifier.secret is None


def test_dingtalk_notifier_init_with_secret():
    """Test DingTalk notifier initialization with secret."""
    notifier = DingTalkNotifier(
        webhook_url="https://test.com/webhook",
        secret="test_secret"
    )
    assert notifier.webhook_url == "https://test.com/webhook"
    assert notifier.secret == "test_secret"


def test_dingtalk_notifier_init_from_env(monkeypatch):
    """Test DingTalk notifier initialization from environment variables."""
    monkeypatch.setenv("DINGTALK_WEBHOOK_URL", "https://env.com/webhook")
    monkeypatch.setenv("DINGTALK_SECRET", "env_secret")
    
    notifier = DingTalkNotifier()
    assert notifier.webhook_url == "https://env.com/webhook"
    assert notifier.secret == "env_secret"


def test_dingtalk_notifier_init_no_config():
    """Test DingTalk notifier initialization without config."""
    notifier = DingTalkNotifier()
    assert notifier.webhook_url is None


def test_dingtalk_notifier_send_notification_success(dingtalk_notifier, sample_entry):
    """Test successful notification sending."""
    with patch("src.storages.dingtalk_client.httpx.Client") as mock_client_class:
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post = Mock(return_value=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post = mock_post
        mock_client_class.return_value.__enter__.return_value = mock_client_instance
        mock_client_class.return_value.__exit__ = Mock(return_value=None)
        
        result = dingtalk_notifier.send_notification(sample_entry)
        
        assert result is True
        mock_post.assert_called_once()


def test_dingtalk_notifier_send_notification_no_webhook(sample_entry):
    """Test notification sending without webhook URL."""
    notifier = DingTalkNotifier()
    result = notifier.send_notification(sample_entry)
    assert result is False


def test_dingtalk_notifier_send_notification_with_secret(dingtalk_notifier, sample_entry):
    """Test notification sending with secret signature."""
    dingtalk_notifier.secret = "test_secret"
    
    with patch("src.storages.dingtalk_client.httpx.Client") as mock_client_class:
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post = Mock(return_value=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post = mock_post
        mock_client_class.return_value.__enter__.return_value = mock_client_instance
        mock_client_class.return_value.__exit__ = Mock(return_value=None)
        
        import time
        with patch.object(time, "time", return_value=1000.0):
            result = dingtalk_notifier.send_notification(sample_entry)
            
            assert result is True
            # Verify post was called
            mock_post.assert_called_once()


def test_dingtalk_notifier_send_notification_error(dingtalk_notifier, sample_entry):
    """Test notification sending handles errors."""
    with patch("src.storages.dingtalk_client.httpx.Client") as mock_client_class:
        mock_post = Mock(side_effect=Exception("API Error"))
        mock_client_instance = Mock()
        mock_client_instance.post = mock_post
        mock_client_class.return_value.__enter__.return_value = mock_client_instance
        mock_client_class.return_value.__exit__ = Mock(return_value=None)
        
        result = dingtalk_notifier.send_notification(sample_entry)
        assert result is False


@pytest.mark.asyncio
async def test_dingtalk_notifier_send_notification_async_success(dingtalk_notifier, sample_entry):
    """Test successful async notification sending."""
    with patch("src.storages.dingtalk_client.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        result = await dingtalk_notifier.send_notification_async(sample_entry)
        
        assert result is True
        mock_client_instance.__aenter__.return_value.post.assert_called_once()


@pytest.mark.asyncio
async def test_dingtalk_notifier_send_notification_async_no_webhook(sample_entry):
    """Test async notification sending without webhook URL."""
    notifier = DingTalkNotifier()
    result = await notifier.send_notification_async(sample_entry)
    assert result is False


@pytest.mark.asyncio
async def test_dingtalk_notifier_send_notification_async_with_secret(dingtalk_notifier, sample_entry):
    """Test async notification sending with secret signature."""
    dingtalk_notifier.secret = "test_secret"
    
    with patch("src.storages.dingtalk_client.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        import time
        with patch.object(time, "time", return_value=1000.0):
            result = await dingtalk_notifier.send_notification_async(sample_entry)
            
            assert result is True


@pytest.mark.asyncio
async def test_dingtalk_notifier_send_notification_async_error(dingtalk_notifier, sample_entry):
    """Test async notification sending handles errors."""
    with patch("src.storages.dingtalk_client.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.post = AsyncMock(side_effect=Exception("API Error"))
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        result = await dingtalk_notifier.send_notification_async(sample_entry)
        assert result is False


def test_dingtalk_notifier_message_content(dingtalk_notifier, sample_entry):
    """Test notification message content format."""
    with patch("src.storages.dingtalk_client.httpx.Client") as mock_client_class:
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post = Mock(return_value=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post = mock_post
        mock_client_class.return_value.__enter__.return_value = mock_client_instance
        mock_client_class.return_value.__exit__ = Mock(return_value=None)
        
        dingtalk_notifier.send_notification(sample_entry)
        
        # Verify message structure
        call_args = mock_post.call_args
        message = call_args[1]["json"]
        
        assert message["msgtype"] == "markdown"
        assert "markdown" in message
        assert "title" in message["markdown"]
        assert "text" in message["markdown"]
        assert "Test Article Title" in message["markdown"]["text"]
        assert "AI" in message["markdown"]["text"]
        assert "High" in message["markdown"]["text"]

