"""Settings read from the environment.

Nothing here requires a key. Every key is optional so the app always boots and shows its main
screen; a feature that needs a missing key reports "not set" instead of failing at startup.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class Settings:
    sarvam_api_key: str
    google_api_key: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    public_base_url: str
    judge_token: str
    calls_enabled: bool

    @property
    def voice_ready(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def phone_ready(self) -> bool:
        return bool(
            self.sarvam_api_key
            and self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
            and self.public_base_url
            and self.calls_enabled
        )

    def status(self) -> dict:
        """What the UI shows. Names which key is missing, never any key's value."""

        def state(ok: bool, missing: str) -> dict:
            return {"ready": ok, "reason": "" if ok else missing}

        return {
            "voice": state(self.voice_ready, "SARVAM_API_KEY not set"),
            "extract": state(
                bool(self.google_api_key),
                "GOOGLE_API_KEY not set: rules-only extraction",
            ),
            "phone": state(
                self.phone_ready,
                "Phone calls off: Twilio keys, PUBLIC_BASE_URL or CALLS_ENABLED not set",
            ),
            "text": state(True, ""),
            "replay": state(True, ""),
        }


def load_settings() -> Settings:
    return Settings(
        sarvam_api_key=_get("SARVAM_API_KEY"),
        google_api_key=_get("GOOGLE_API_KEY"),
        twilio_account_sid=_get("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_get("TWILIO_AUTH_TOKEN"),
        twilio_from_number=_get("TWILIO_FROM_NUMBER"),
        public_base_url=_get("PUBLIC_BASE_URL").rstrip("/"),
        judge_token=_get("JUDGE_TOKEN"),
        calls_enabled=_get("CALLS_ENABLED").lower() in {"1", "true", "yes"},
    )
