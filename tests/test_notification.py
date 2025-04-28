import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules
from utils.notification import NotificationManager
from utils.logger import Logger
from config import Config

class TestNotificationManager(unittest.TestCase):
    """Test cases for the NotificationManager class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock configuration
        self.config = Config()
        self.config.enable_notifications = True
        self.config.telegram_bot_token = "test_token"
        self.config.telegram_chat_id = "test_chat_id"
        self.config.email_sender = "test@example.com"
        self.config.email_password = "test_password"
        self.config.email_recipient = "recipient@example.com"
        
        # Mock logger
        self.logger = MagicMock()
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.warning = MagicMock()
        
        # Create NotificationManager instance
        self.notification_manager = NotificationManager(self.logger, self.config)
    
    @patch('utils.notification.requests.post')
    def test_send_telegram(self, mock_post):
        """Test sending Telegram notification"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Call method
        result = self.notification_manager._send_telegram("Test message")
        
        # Verify
        mock_post.assert_called_once()
        self.assertTrue(result)
        
        # Mock failed response
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        
        # Call method
        result = self.notification_manager._send_telegram("Test message")
        
        # Verify
        self.assertFalse(result)
    
    @patch('utils.notification.smtplib.SMTP')
    def test_send_email(self, mock_smtp):
        """Test sending email notification"""
        # Mock SMTP server
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Call method
        result = self.notification_manager._send_email("Test subject", "Test message")
        
        # Verify
        mock_smtp.assert_called_once()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()
        self.assertTrue(result)
        
        # Mock exception
        mock_smtp.side_effect = Exception("SMTP error")
        
        # Call method
        result = self.notification_manager._send_email("Test subject", "Test message")
        
        # Verify
        self.assertFalse(result)
    
    @patch('utils.notification.NotificationManager._send_telegram')
    @patch('utils.notification.NotificationManager._send_email')
    def test_send_notification(self, mock_send_email, mock_send_telegram):
        """Test sending notification"""
        # Mock successful sending
        mock_send_telegram.return_value = True
        mock_send_email.return_value = True
        
        # Call method
        result = self.notification_manager.send_notification("Test message", "INFO")
        
        # Verify
        mock_send_telegram.assert_called_once()
        mock_send_email.assert_not_called()
        self.assertTrue(result)
        
        # Test with ERROR level
        mock_send_telegram.reset_mock()
        mock_send_email.reset_mock()
        
        # Call method
        result = self.notification_manager.send_notification("Test message", "ERROR")
        
        # Verify
        mock_send_telegram.assert_called_once()
        mock_send_email.assert_called_once()
        self.assertTrue(result)
        
        # Test with notifications disabled
        self.config.enable_notifications = False
        mock_send_telegram.reset_mock()
        mock_send_email.reset_mock()
        
        # Call method
        result = self.notification_manager.send_notification("Test message", "ERROR")
        
        # Verify
        mock_send_telegram.assert_not_called()
        mock_send_email.assert_not_called()
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
