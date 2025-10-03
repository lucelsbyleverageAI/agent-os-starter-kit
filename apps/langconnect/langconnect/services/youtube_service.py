"""YouTube transcript extraction and processing service."""

import logging
import re
import os
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
# Import specific exceptions for better error handling
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound,
    NoTranscriptAvailable,
    NotTranslatable,
    TranslationLanguageNotAvailable,
    CookiePathInvalid,
    CookiesInvalid,
    FailedToCreateConsentCookie,
    YouTubeRequestFailed,
    TooManyRequests
)
from langchain_core.documents import Document
from requests import Session

logger = logging.getLogger(__name__)


@dataclass
class YouTubeTranscript:
    """Container for YouTube transcript data."""
    content: str
    metadata: Dict[str, Any]
    raw_transcript: List[Dict[str, Any]]


class YouTubeProcessingError(Exception):
    """Custom exception for YouTube processing errors."""
    pass


class YouTubeService:
    """Service for extracting and processing YouTube video transcripts."""
    
    def __init__(self):
        """Initialize the YouTube service."""
        self.text_formatter = TextFormatter()
        
        # Initialize Supadata API configuration
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
    
    async def extract_transcript_standard_api(
        self, 
        video_id: str, 
        progress_callback: Optional[callable] = None
    ) -> YouTubeTranscript:
        """Extract transcript using the standard youtube-transcript-api.
        
        Args:
            video_id: YouTube video ID
            progress_callback: Optional callback for progress updates
            
        Returns:
            YouTubeTranscript object with content and metadata
            
        Raises:
            YouTubeProcessingError: If transcript extraction fails
        """
        if progress_callback:
            progress_callback("Trying standard YouTube transcript API")
        
        # Get available transcripts using static method
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get the best available transcript
        transcript = self._get_best_transcript(transcript_list)
        
        if progress_callback:
            progress_callback(f"Found transcript in {transcript.language}")
        
        # Fetch transcript data
        transcript_data = transcript.fetch()
        
        # Process transcript into usable format
        return self._process_standard_transcript_data(
            transcript_data, video_id, transcript
        )
    
    async def extract_transcript_supadata_api(
        self, 
        video_id: str, 
        progress_callback: Optional[callable] = None
    ) -> YouTubeTranscript:
        """Extract transcript using Supadata API as fallback.
        
        Args:
            video_id: YouTube video ID
            progress_callback: Optional callback for progress updates
            
        Returns:
            YouTubeTranscript object with content and metadata
            
        Raises:
            YouTubeProcessingError: If transcript extraction fails
        """
        if not self.supadata_api_key:
            raise YouTubeProcessingError("Supadata API key not configured")
        
        if progress_callback:
            progress_callback("Trying Supadata API as fallback")
        
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
            
            if progress_callback:
                progress_callback("Processing Supadata transcript data")
            
            # Process Supadata response
            return self._process_supadata_transcript_data(data, video_id)
            
        except requests.RequestException as e:
            raise YouTubeProcessingError(f"Supadata API request failed: {str(e)}")
        except (KeyError, ValueError) as e:
            raise YouTubeProcessingError(f"Failed to parse Supadata response: {str(e)}")
    
    async def extract_transcript(
        self, 
        url: str, 
        progress_callback: Optional[callable] = None
    ) -> YouTubeTranscript:
        """Extract transcript from YouTube video using tiered approach.
        
        This method tries multiple approaches in order:
        1. Standard youtube-transcript-api
        2. Supadata API (if configured)
        
        Args:
            url: YouTube video URL
            progress_callback: Optional callback for progress updates
            
        Returns:
            YouTubeTranscript object with content and metadata
            
        Raises:
            YouTubeProcessingError: If all transcript extraction methods fail
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            raise YouTubeProcessingError(f"Invalid YouTube URL format: {url}")
        
        if progress_callback:
            progress_callback(f"Extracting transcript for video: {video_id}")
        
        # Store errors from each attempt
        errors = []
        
        # Attempt 1: Standard YouTube Transcript API
        try:
            if progress_callback:
                progress_callback("Attempting standard YouTube API")
            
            transcript = await self.extract_transcript_standard_api(video_id, progress_callback)
            
            if progress_callback:
                progress_callback("Standard API extraction completed successfully")
            
            return transcript
            
        except TranscriptsDisabled:
            error_msg = f"Transcripts are disabled for video {video_id}"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
            
        except VideoUnavailable:
            error_msg = f"Video {video_id} is unavailable or private"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
            
        except (NoTranscriptFound, NoTranscriptAvailable):
            error_msg = f"No transcripts available for video {video_id}"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
            
        except TooManyRequests:
            error_msg = "Too many requests to YouTube API"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
            
        except YouTubeRequestFailed as e:
            if "no element found" in str(e).lower():
                error_msg = "YouTube blocked the request (rate limiting or restrictions)"
            else:
                error_msg = f"YouTube request failed: {str(e)}"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            if "no element found" in str(e).lower():
                error_msg = "YouTube blocked the request (rate limiting or restrictions)"
            errors.append(f"Standard API: {error_msg}")
            if progress_callback:
                progress_callback(f"Standard API failed: {error_msg}")
        
        # Attempt 2: Supadata API (if configured)
        if self.supadata_api_key:
            try:
                if progress_callback:
                    progress_callback("Attempting Supadata API as fallback")
                
                transcript = await self.extract_transcript_supadata_api(video_id, progress_callback)
                
                if progress_callback:
                    progress_callback("Supadata API extraction completed successfully")
                
                return transcript
                
            except YouTubeProcessingError as e:
                errors.append(f"Supadata API: {str(e)}")
                if progress_callback:
                    progress_callback(f"Supadata API failed: {str(e)}")
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                errors.append(f"Supadata API: {error_msg}")
                if progress_callback:
                    progress_callback(f"Supadata API failed: {error_msg}")
        else:
            errors.append("Supadata API: Not configured (SUPADATA_API_TOKEN missing)")
            if progress_callback:
                progress_callback("Supadata API: Not configured")
        
        # All methods failed
        combined_error = "All transcript extraction methods failed:\n" + "\n".join(errors)
        if progress_callback:
            progress_callback("All extraction methods failed")
        
        raise YouTubeProcessingError(combined_error)
    
    def _get_best_transcript(self, transcript_list) -> Any:
        """Get the best available transcript from the list.
        
        Args:
            transcript_list: List of available transcripts
            
        Returns:
            Best transcript object
        """
        # Preference order: manual English, manual any language, generated English, generated any
        try:
            # Try manual English first
            return transcript_list.find_transcript(['en'])
        except:
            try:
                # Try any manual transcript
                return transcript_list.find_manually_created_transcript(['en', 'es', 'fr', 'de'])
            except:
                try:
                    # Try generated English
                    return transcript_list.find_generated_transcript(['en'])
                except:
                    # Try any generated transcript
                    return transcript_list.find_generated_transcript(['es', 'fr', 'de'])
    
    def _process_standard_transcript_data(
        self, 
        transcript_data: List[Dict[str, Any]], 
        video_id: str, 
        transcript_obj: Any
    ) -> YouTubeTranscript:
        """Process raw transcript data from standard API into structured format.
        
        Args:
            transcript_data: Raw transcript data from YouTube API
            video_id: YouTube video ID
            transcript_obj: Transcript object with metadata
            
        Returns:
            Processed YouTubeTranscript object
        """
        # Flatten transcript into continuous text for better semantic chunking
        full_text = " ".join([entry['text'] for entry in transcript_data])
        
        # Clean up text (remove extra whitespace, fix common issues)
        full_text = self._clean_transcript_text(full_text)
        
        # Create metadata
        metadata = {
            'source_type': 'youtube',
            'video_id': video_id,
            'language': transcript_obj.language,
            'language_code': transcript_obj.language_code,
            'is_generated': transcript_obj.is_generated,
            'is_translatable': transcript_obj.is_translatable,
            'content_type': 'video_transcript',
            'transcript_entries': len(transcript_data),
            'processing_approach': 'flattened_text',
            'extraction_method': 'standard_api',
        }
        
        # Add duration if available
        if transcript_data:
            total_duration = max(
                entry.get('start', 0) + entry.get('duration', 0) 
                for entry in transcript_data
            )
            metadata['duration_seconds'] = int(total_duration)
            metadata['estimated_reading_time'] = self._estimate_reading_time(full_text)
        
        return YouTubeTranscript(
            content=full_text,
            metadata=metadata,
            raw_transcript=transcript_data
        )
    
    def _process_supadata_transcript_data(
        self, 
        supadata_response: Dict[str, Any], 
        video_id: str
    ) -> YouTubeTranscript:
        """Process transcript data from Supadata API into structured format.
        
        Args:
            supadata_response: Response from Supadata API
            video_id: YouTube video ID
            
        Returns:
            Processed YouTubeTranscript object
        """
        content_entries = supadata_response.get('content', [])
        if not content_entries:
            raise YouTubeProcessingError("No transcript content found in Supadata response")
        
        # Extract text content for flattened approach
        full_text = " ".join([entry.get('text', '').strip() for entry in content_entries if entry.get('text')])
        
        # Clean up text
        full_text = self._clean_transcript_text(full_text)
        
        # Convert Supadata format to standard transcript format for compatibility
        standard_format = []
        for entry in content_entries:
            if entry.get('text'):
                offset_seconds = entry.get('offset', 0) / 1000  # Convert milliseconds to seconds
                standard_format.append({
                    'text': entry['text'],
                    'start': offset_seconds,
                    'duration': 2.0  # Estimate duration as 2 seconds
                })
        
        # Create metadata
        metadata = {
            'source_type': 'youtube',
            'video_id': video_id,
            'language': 'English',  # Supadata typically returns English
            'language_code': 'en',
            'is_generated': True,   # Assume generated since we don't have this info
            'is_translatable': False,
            'content_type': 'video_transcript',
            'transcript_entries': len(content_entries),
            'processing_approach': 'flattened_text',
            'extraction_method': 'supadata_api',
            'estimated_reading_time': self._estimate_reading_time(full_text)
        }
        
        # Add duration if available
        if content_entries:
            last_entry = max(content_entries, key=lambda x: x.get('offset', 0))
            metadata['duration_seconds'] = int(last_entry.get('offset', 0) / 1000)
        
        return YouTubeTranscript(
            content=full_text,
            metadata=metadata,
            raw_transcript=standard_format
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
        
        # Clean up punctuation
        text = re.sub(r'\s+([,.!?])', r'\1', text)
        
        return text.strip()
    
    def _estimate_reading_time(self, text: str) -> int:
        """Estimate reading time in seconds based on average reading speed.
        
        Args:
            text: Text to estimate reading time for
            
        Returns:
            Estimated reading time in seconds
        """
        # Average reading speed: 200 words per minute
        word_count = len(text.split())
        reading_time_minutes = word_count / 200
        return int(reading_time_minutes * 60)
    
    def get_video_metadata(self, video_id: str) -> Dict[str, Any]:
        """Get basic video metadata (without requiring YouTube Data API).
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Dictionary with basic video metadata
        """
        return {
            'video_id': video_id,
            'platform': 'youtube',
            'url': f'https://www.youtube.com/watch?v={video_id}',
            'content_type': 'video_transcript',
            'source_type': 'youtube'
        }
    
    async def process_youtube_url(
        self,
        url: str,
        title: str = "",
        description: str = "",
        progress_callback: Optional[callable] = None
    ) -> List[Document]:
        """Process a YouTube URL into LangChain documents using tiered transcript extraction.
        
        Args:
            url: YouTube video URL
            title: Custom title for the document
            description: Custom description for the document
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of processed Document objects
            
        Raises:
            YouTubeProcessingError: If processing fails
        """
        try:
            if progress_callback:
                progress_callback("Starting YouTube video processing")
            
            # Extract transcript using tiered approach
            transcript = await self.extract_transcript(url, progress_callback)
            
            if progress_callback:
                progress_callback("Creating document from transcript")
            
            # Prepare document metadata
            doc_metadata = transcript.metadata.copy()
            doc_metadata.update({
                'url': url,
                'title': title or f"YouTube Video {transcript.metadata['video_id']}",
                'description': description or "",  # Empty description for user to fill in
                'source_name': url,
            })
            
            # Create LangChain document
            document = Document(
                page_content=transcript.content,
                metadata=doc_metadata
            )
            
            if progress_callback:
                progress_callback("YouTube processing completed successfully")
            
            logger.info(f"Successfully processed YouTube video {transcript.metadata['video_id']} "
                       f"using {transcript.metadata['extraction_method']}")
            
            return [document]
            
        except YouTubeProcessingError as e:
            logger.error(f"YouTube processing error for {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing YouTube URL {url}: {e}")
            raise YouTubeProcessingError(f"Unexpected error processing YouTube URL: {str(e)}")
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported YouTube URL formats.
        
        Returns:
            List of supported URL format descriptions
        """
        return [
            "https://www.youtube.com/watch?v=VIDEO_ID",
            "https://youtu.be/VIDEO_ID",
            "https://www.youtube.com/embed/VIDEO_ID",
            "https://www.youtube.com/v/VIDEO_ID",
            "youtube.com/watch?v=VIDEO_ID (without protocol)",
        ]
    
    def get_processing_info(self) -> Dict[str, Any]:
        """Get information about available processing methods.
        
        Returns:
            Dictionary with processing method information
        """
        return {
            "methods": [
                {
                    "name": "Standard YouTube API",
                    "description": "Official YouTube transcript API",
                    "priority": 1,
                    "pros": ["Fast", "Official", "Multiple languages"],
                    "cons": ["Subject to rate limiting", "May be blocked"]
                },
                {
                    "name": "Supadata API",
                    "description": "Third-party transcript service",
                    "priority": 2,
                    "configured": bool(self.supadata_api_key),
                    "pros": ["Reliable", "Less likely to be blocked"],
                    "cons": ["Requires API key", "May have usage limits"]
                }
            ],
            "output_format": "flattened_text",
            "chunking_recommendation": "Use RecursiveCharacterTextSplitter for optimal results"
        } 