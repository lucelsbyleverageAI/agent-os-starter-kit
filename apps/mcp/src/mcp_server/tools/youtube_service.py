"""YouTube transcript extraction service for MCP server."""

import logging
import re
import os
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class YouTubeTranscript:
    """Container for YouTube transcript data."""
    content: str
    metadata: Dict[str, Any]
    word_count: int


class YouTubeService:
    """Service for extracting YouTube video transcripts using Supadata API."""

    def __init__(self):
        """Initialize the YouTube service."""
        self.supadata_api_url = "https://api.supadata.ai/v1/youtube/transcript"
        self.supadata_api_key = os.getenv('SUPADATA_API_TOKEN')

    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats.

        Args:
            url: YouTube URL in various formats

        Returns:
            Video ID if found, None otherwise
        """
        patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def is_youtube_url(self, url: str) -> bool:
        """Check if a URL is a YouTube URL.

        Args:
            url: URL to check

        Returns:
            True if the URL is a YouTube URL
        """
        return self.extract_video_id(url) is not None

    async def extract_transcript(
        self,
        url: str,
        max_words: Optional[int] = None,
        offset_words: int = 0
    ) -> YouTubeTranscript:
        """Extract transcript from YouTube video using Supadata API.

        Args:
            url: YouTube video URL
            max_words: Maximum number of words to return (None for all)
            offset_words: Number of words to skip from beginning

        Returns:
            YouTubeTranscript object with content and metadata

        Raises:
            Exception: If transcript extraction fails
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError(f"Invalid YouTube URL format: {url}")

        if not self.supadata_api_key:
            raise ValueError("Supadata API key not configured (SUPADATA_API_TOKEN missing)")

        logger.info(f"Extracting transcript for YouTube video: {video_id}")

        try:
            headers = {
                'x-api-key': self.supadata_api_key
            }

            response = requests.get(
                f"{self.supadata_api_url}?videoId={video_id}",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Process Supadata response
            return self._process_transcript_data(data, video_id, url, max_words, offset_words)

        except requests.RequestException as e:
            logger.error(f"Supadata API request failed for video {video_id}: {str(e)}")
            raise Exception(f"Failed to fetch YouTube transcript: {str(e)}")
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse Supadata response for video {video_id}: {str(e)}")
            raise Exception(f"Failed to parse YouTube transcript data: {str(e)}")

    def _process_transcript_data(
        self,
        supadata_response: Dict[str, Any],
        video_id: str,
        url: str,
        max_words: Optional[int] = None,
        offset_words: int = 0
    ) -> YouTubeTranscript:
        """Process transcript data from Supadata API.

        Args:
            supadata_response: Response from Supadata API
            video_id: YouTube video ID
            url: Original YouTube URL
            max_words: Maximum number of words to return
            offset_words: Number of words to skip from beginning

        Returns:
            Processed YouTubeTranscript object
        """
        content_entries = supadata_response.get('content', [])
        if not content_entries:
            raise ValueError("No transcript content found in Supadata response")

        # Extract and clean text content
        full_text = " ".join([
            entry.get('text', '').strip()
            for entry in content_entries
            if entry.get('text')
        ])

        # Clean up text
        full_text = self._clean_transcript_text(full_text)

        # Calculate total word count
        all_words = full_text.split()
        total_word_count = len(all_words)

        # Apply word limits if specified
        if max_words is not None or offset_words > 0:
            words = all_words[offset_words:offset_words + max_words] if max_words else all_words[offset_words:]
            processed_text = " ".join(words)
            actual_word_count = len(words)
        else:
            processed_text = full_text
            actual_word_count = total_word_count

        # Create metadata
        metadata = {
            'source_type': 'youtube',
            'video_id': video_id,
            'url': url,
            'total_word_count': total_word_count,
            'returned_word_count': actual_word_count,
            'offset_words': offset_words,
            'max_words_applied': max_words,
            'has_more_content': offset_words + actual_word_count < total_word_count,
            'extraction_method': 'supadata_api',
        }

        # Add duration if available
        if content_entries:
            last_entry = max(content_entries, key=lambda x: x.get('offset', 0), default=None)
            if last_entry:
                metadata['duration_seconds'] = int(last_entry.get('offset', 0) / 1000)

        return YouTubeTranscript(
            content=processed_text,
            metadata=metadata,
            word_count=actual_word_count
        )

    def _clean_transcript_text(self, text: str) -> str:
        """Clean and normalize transcript text.

        Args:
            text: Raw transcript text

        Returns:
            Cleaned transcript text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove common artifacts
        text = text.replace('[Music]', '').replace('[Applause]', '')
        text = text.replace('[music]', '').replace('[applause]', '')

        # Clean up punctuation
        text = re.sub(r'\s+([,.!?])', r'\1', text)

        return text.strip()


# Global instance
youtube_service = YouTubeService()