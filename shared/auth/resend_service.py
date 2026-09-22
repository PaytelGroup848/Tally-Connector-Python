"""
CtrlBooks - Resend Email OTP Service
------------------------------------------------
Sends Email OTP verification codes via Resend API (https://api.resend.com/emails).
Falls back cleanly to logging OTP in console/logs when test or empty API key is present.
"""

import os
import httpx
from typing import Dict, Any
from shared.config import get_settings
from shared.logging_config import get_logger

logger = get_logger("app.auth.resend")

class ResendService:
    def __init__(self):
        self.api_url = "https://api.resend.com/emails"

    def _get_api_key(self) -> str:
        env_key = os.getenv("RESEND_API_KEY", "")
        if env_key:
            return env_key.strip()
        settings_key = get_settings().resend_api_key or ""
        return settings_key.strip()

    def send_otp_email(self, to_email: str, otp_code: str) -> Dict[str, Any]:
        """
        Delivers 6-digit OTP code to specified recipient email address via Resend API.
        """
        clean_email = to_email.strip().lower()
        api_key = self._get_api_key()

        logger.info(f"🔑 [EMAIL OTP GENERATED] Recipient: {clean_email} | OTP Code: {otp_code}")

        if not api_key or api_key == "re_123456789":
            logger.warning(f"Using default/mock RESEND_API_KEY. OTP for {clean_email} logged above.")
            return {"status": "sent_mock", "email": clean_email, "message": "OTP logged for development"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "from": "CtrlBooks <onboarding@resend.dev>",
            "to": [clean_email],
            "subject": f"{otp_code} is your CtrlBooks Login OTP",
            "html": f"""
                <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                    <h2 style="color: #00C853; margin-bottom: 10px;">CtrlBooks</h2>
                    <p style="font-size: 14px; color: #475569;">Use the following One-Time Password (OTP) to complete your login:</p>
                    <div style="background-color: #f1f5f9; padding: 15px; text-align: center; border-radius: 6px; margin: 20px 0;">
                        <span style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #0f172a;">{otp_code}</span>
                    </div>
                    <p style="font-size: 12px; color: #94a3b8;">This OTP is valid for 5 minutes. Do not share this code with anyone.</p>
                </div>
            """
        }

        try:
            response = httpx.post(self.api_url, headers=headers, json=payload, timeout=10.0)
            if response.status_code in (200, 201):
                res_data = response.json()
                logger.info(f"Resend Email sent successfully to {clean_email} (ID: {res_data.get('id')})")
                return {"status": "sent", "email": clean_email, "resend_id": res_data.get("id")}
            else:
                logger.error(f"Resend API error ({response.status_code}): {response.text}")
                return {"status": "fallback", "email": clean_email, "reason": response.text}
        except Exception as e:
            logger.error(f"Failed to connect to Resend API: {e}")
            return {"status": "fallback", "email": clean_email, "reason": str(e)}

resend_service = ResendService()
