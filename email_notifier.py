# -*- coding: utf-8 -*-
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List
from config import ScraperConfig
from logger import logger

class EmailNotifier:
    def __init__(self, email_to: Optional[str] = None):
        self.email_from = ScraperConfig.EMAIL_FROM
        self.email_password = ScraperConfig.EMAIL_PASSWORD
        self.email_to = email_to
        self.smtp_server = ScraperConfig.SMTP_SERVER
        self.smtp_port = ScraperConfig.SMTP_PORT
    
    def is_configured(self) -> bool:
        return bool(self.email_from and self.email_password and self.email_to)
    
    def send_scraping_complete(self, keyword: str, nb_profils: int, 
                              nb_invitations: int = 0, ecoles: Optional[List[str]] = None,
                              duration: Optional[float] = None, errors: Optional[List[str]] = None) -> bool:
        if not self.is_configured():
            logger.warning("Notifications email non configurées")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"✅ Scraping LinkedIn terminé - {nb_profils} profils"
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            
            html = self._create_html_report(keyword, nb_profils, nb_invitations, 
                                           ecoles, duration, errors)
            part = MIMEText(html, 'html')
            msg.attach(part)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email envoyé à {self.email_to}")
            return True
        except Exception as e:
            logger.error(f"Erreur envoi email: {e}")
            return False
    
    def _create_html_report(self, keyword, nb_profils, nb_invitations, 
                           ecoles, duration, errors):
        duration_str = ""
        if duration:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            duration_str = f"{minutes}m {seconds}s"
        
        ecoles_str = ", ".join(ecoles) if ecoles else "Aucune"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #667eea;">💼 LinkedIn Scraper - Rapport</h2>
            <p><strong>Date:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
            <div style="background: #f0f0f0; padding: 15px; margin: 20px 0;">
                <h3>{nb_profils} Profils Scrapés</h3>
                <p><strong>Invitations:</strong> {nb_invitations}</p>
                <p><strong>Mots-clés:</strong> {keyword or 'Aucun'}</p>
                <p><strong>Écoles:</strong> {ecoles_str}</p>
                {f'<p><strong>Durée:</strong> {duration_str}</p>' if duration_str else ''}
            </div>
        </body>
        </html>
        """
        return html
