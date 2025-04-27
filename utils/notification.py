import os
import logging
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

class NotificationManager:
    def __init__(self, logger, config):
        """
        Initialize NotificationManager with logger and config
        
        Args:
            logger: Logger instance
            config: Configuration instance
        """
        self.logger = logger
        self.config = config
        self.logger.info("NotificationManager: Initializing notification manager")
        
        # Load environment variables
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'auth', '.env'))
        
        # Telegram settings
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or self.config.telegram_bot_token
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID') or self.config.telegram_chat_id
        
        # Email settings
        self.email_sender = os.getenv('EMAIL_SENDER') or self.config.email_sender
        self.email_password = os.getenv('EMAIL_PASSWORD') or self.config.email_password
        self.email_recipient = os.getenv('EMAIL_RECIPIENT') or self.config.email_recipient
        self.email_smtp_server = self.config.email_smtp_server
        self.email_smtp_port = self.config.email_smtp_port
        
        self.logger.info("NotificationManager: Notification manager initialized")
    
    def send_notification(self, message, level="INFO", send_email=False):
        """
        Send notification via Telegram and optionally email
        
        Args:
            message: Message to send
            level: Message level (INFO, WARNING, ERROR, CRITICAL)
            send_email: Whether to send email notification
            
        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.config.enable_notifications:
            return True
            
        success = True
        
        # Add level prefix to message
        prefixed_message = f"[{level}] {message}"
        
        # Send Telegram notification
        if self.telegram_bot_token and self.telegram_chat_id:
            telegram_success = self._send_telegram(prefixed_message)
            if not telegram_success:
                self.logger.error("NotificationManager: Failed to send Telegram notification")
                success = False
        
        # Send email notification for higher severity levels or if explicitly requested
        if send_email or level in ["ERROR", "CRITICAL"]:
            if self.email_sender and self.email_password and self.email_recipient:
                email_success = self._send_email(f"NSE Trading Alert: {level}", prefixed_message)
                if not email_success:
                    self.logger.error("NotificationManager: Failed to send email notification")
                    success = False
        
        return success
    
    def _send_telegram(self, message):
        """
        Send message via Telegram
        
        Args:
            message: Message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                self.logger.info("NotificationManager: Telegram notification sent successfully")
                return True
            else:
                self.logger.error(f"NotificationManager: Failed to send Telegram notification: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"NotificationManager: Error sending Telegram notification: {str(e)}")
            return False
    
    def _send_email(self, subject, message):
        """
        Send message via email
        
        Args:
            subject: Email subject
            message: Email message
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_sender
            msg['To'] = self.email_recipient
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(self.email_smtp_server, self.email_smtp_port)
            server.starttls()
            server.login(self.email_sender, self.email_password)
            server.send_message(msg)
            server.quit()
            
            self.logger.info("NotificationManager: Email notification sent successfully")
            return True
        except Exception as e:
            self.logger.error(f"NotificationManager: Error sending email notification: {str(e)}")
            return False
