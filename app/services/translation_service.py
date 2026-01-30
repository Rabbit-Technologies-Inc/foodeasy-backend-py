# app/services/translation_service.py

"""
Translation service: translates text from any language to a target language.
Uses Google Cloud Translation API v3 first; falls back to googletrans on failure.
Returns both the original and translated values.
"""

import json
import os
import asyncio
from typing import Optional

from dotenv import load_dotenv
from google.cloud import translate_v3
from google.oauth2 import service_account
from googletrans import Translator

load_dotenv()


class TranslationResult:
    """Result of a translation: original text and translated text."""

    def __init__(self, original: str, translated: str, source_language: Optional[str] = None):
        self.original = original
        self.translated = translated
        self.source_language = source_language

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "translated": self.translated,
            "source_language": self.source_language,
        }


class TranslationService:
    """
    Translates text from any language to a target language.
    Primary: Google Cloud Translation API v3.
    Fallback: googletrans.
    """

    def __init__(self):
        self._translate_client: Optional[translate_v3.TranslationServiceClient] = None
        self._project_id: Optional[str] = None
        self._googletrans_translator: Optional[Translator] = None
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize Cloud Translation v3 and googletrans clients."""
        # Google Cloud Translation v3
        google_credentials = os.getenv("GOOGLE_CLOUD_CREDENTIALS_JSON") or os.getenv(
            "FIREBASE_CREDENTIALS_JSON"
        )
        google_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

        try:
            credentials = None
            if google_credentials:
                try:
                    creds_dict = json.loads(google_credentials)
                    credentials = service_account.Credentials.from_service_account_info(
                        creds_dict
                    )
                    self._project_id = creds_dict.get("project_id") or google_project_id
                except json.JSONDecodeError:
                    if os.path.exists(google_credentials):
                        credentials = service_account.Credentials.from_service_account_file(
                            google_credentials
                        )
                        with open(google_credentials, "r") as f:
                            creds_dict = json.load(f)
                            self._project_id = (
                                creds_dict.get("project_id") or google_project_id
                            )

            if not self._project_id:
                self._project_id = google_project_id

            if credentials and self._project_id:
                self._translate_client = translate_v3.TranslationServiceClient(
                    credentials=credentials
                )
            elif self._project_id:
                self._translate_client = translate_v3.TranslationServiceClient()
        except Exception as e:
            print(f"Warning: Could not initialize Google Cloud Translation client: {e}")
            self._translate_client = None

        # googletrans fallback
        try:
            self._googletrans_translator = Translator()
        except Exception as e:
            print(f"Warning: Could not initialize googletrans fallback: {e}")
            self._googletrans_translator = None

    def _translate_with_v3(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> Optional[TranslationResult]:
        """
        Translate using Google Cloud Translation API v3.
        Returns TranslationResult or None on failure.
        """
        if not self._translate_client or not self._project_id or not text.strip():
            return None

        try:
            parent = f"projects/{self._project_id}/locations/global"
            kwargs = {
                "contents": [text],
                "parent": parent,
                "mime_type": "text/plain",
                "target_language_code": target_language,
            }
            if source_language:
                kwargs["source_language_code"] = source_language
            # If source_language is None, API will auto-detect

            response = self._translate_client.translate_text(**kwargs)
            if not response.translations:
                return None

            translated_text = response.translations[0].translated_text
            detected_lang = None
            if response.translations[0].detected_language_code:
                detected_lang = response.translations[0].detected_language_code

            return TranslationResult(
                original=text,
                translated=translated_text,
                source_language=detected_lang or source_language,
            )
        except Exception as e:
            print(f"Cloud Translation API error: {e}")
            return None

    def _translate_with_googletrans(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> Optional[TranslationResult]:
        """
        Translate using googletrans.
        Returns TranslationResult or None on failure.
        """
        if not self._googletrans_translator or not text.strip():
            return None

        try:
            src = source_language if source_language else "auto"
            result = self._googletrans_translator.translate(
                text, dest=target_language, src=src
            )
            if result and result.text is not None:
                return TranslationResult(
                    original=text,
                    translated=result.text,
                    source_language=getattr(result, "src", None) or source_language,
                )
        except Exception as e:
            print(f"Googletrans error: {e}")
        return None

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> TranslationResult:
        """
        Translate text from any language to the target language.
        Uses translate_v3 first; if it fails, uses googletrans.

        :param text: Text to translate.
        :param target_language: Target language code (e.g. "en", "hi", "es").
        :param source_language: Optional source language code. If None, language is auto-detected.
        :return: TranslationResult with original and translated values (and optional source_language).
        """
        if not text or not text.strip():
            return TranslationResult(original=text, translated=text, source_language=source_language)

        if not target_language or not str(target_language).strip():
            return TranslationResult(original=text, translated=text, source_language=source_language)

        target_language = str(target_language).strip()
        if target_language.lower() == "en":
            # Normalize for comparison; some APIs use "en" vs "en-US"
            target_language = "en"

        # Try Cloud Translation v3 first
        result = self._translate_with_v3(text, target_language, source_language)
        if result is not None:
            return result

        # Fallback to googletrans
        result = self._translate_with_googletrans(text, target_language, source_language)
        if result is not None:
            return result

        # Both failed: return original as both
        return TranslationResult(
            original=text, translated=text, source_language=source_language
        )

    async def translate_async(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> TranslationResult:
        """
        Async wrapper for translate. Runs the sync translate in a thread.
        """
        return await asyncio.to_thread(
            self.translate, text, target_language, source_language
        )


# Singleton instance for easy import
translation_service = TranslationService()
