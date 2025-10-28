"""AI-powered image analysis service using OpenAI Vision API."""

import logging
import base64
from typing import Union
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Model configuration
VISION_MODEL = "gpt-4o-mini"

VISION_SYSTEM_PROMPT = """You are an image cataloging assistant for an AI-powered knowledge base.
Your task is to analyze images and generate structured metadata that will help AI agents understand and search the visual content.

Generate three distinct pieces of information:

1. **Title**: A concise 2-3 word label that captures the primary subject or theme
   - Examples: "Mountain Landscape", "Team Meeting", "Product Diagram"

2. **Short Description**: A brief 1-2 sentence summary (max 150 characters)
   - Focus on the main subject and key context
   - Examples: "A snow-covered mountain peak at sunset with pine trees in foreground."

3. **Detailed Description**: A comprehensive analysis (3-5 sentences, 300-500 characters)
   - Describe visual elements, composition, colors, mood, and context
   - Include relevant details that would help semantic search
   - Mention any text, objects, people, or notable features
   - Provide context about what the image depicts and its potential significance

Use clear, descriptive language optimized for semantic search and agent comprehension."""


class ImageMetadata(BaseModel):
    """Structured metadata extracted from an image."""

    title: str = Field(
        ...,
        description="Concise 2-3 word title capturing the primary subject"
    )
    short_description: str = Field(
        ...,
        description="Brief 1-2 sentence summary (max 150 characters)"
    )
    detailed_description: str = Field(
        ...,
        description="Comprehensive 3-5 sentence analysis (300-500 characters) for semantic search"
    )


class VisionAnalysisService:
    """Service for analyzing images using OpenAI Vision API."""

    def __init__(self):
        """Initialize the vision analysis service."""
        self.client = AsyncOpenAI()
        self.model = VISION_MODEL

    def _encode_image_base64(self, image_data: bytes) -> str:
        """Encode image data as base64 string.

        Args:
            image_data: Raw image bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_data).decode('utf-8')

    async def analyze_image(
        self,
        image_data: bytes,
        image_format: str = "jpeg",
        fallback_title: str = "Untitled Image"
    ) -> ImageMetadata:
        """Analyze an image and extract metadata using Vision API.

        Args:
            image_data: Raw image bytes
            image_format: Image format (jpeg, png, webp, etc.)
            fallback_title: Title to use if analysis fails

        Returns:
            ImageMetadata with extracted title, short description, and detailed description

        Raises:
            Exception: If analysis fails
        """
        try:
            # Encode image as base64
            base64_image = self._encode_image_base64(image_data)

            # Call Vision API with structured output
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this image and provide the structured metadata."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": "high"  # Use high detail for better analysis
                                }
                            }
                        ]
                    }
                ],
                response_format=ImageMetadata,
                temperature=0.3,  # Lower temperature for consistent output
                max_tokens=500,  # Enough for detailed description
            )

            metadata = completion.choices[0].message.parsed

            # Validate metadata
            if not metadata.title or not metadata.short_description or not metadata.detailed_description:
                raise ValueError("Generated metadata is incomplete")

            # Enforce length limits
            if len(metadata.short_description) > 150:
                metadata.short_description = metadata.short_description[:147] + "..."

            if len(metadata.detailed_description) > 500:
                metadata.detailed_description = metadata.detailed_description[:497] + "..."

            logger.info(
                f"Analyzed image - Title: '{metadata.title}', "
                f"Short: '{metadata.short_description[:50]}...', "
                f"Detailed: {len(metadata.detailed_description)} chars"
            )

            return metadata

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            # Return fallback metadata
            return ImageMetadata(
                title=fallback_title,
                short_description=f"Image file: {fallback_title}",
                detailed_description=f"An uploaded image file named {fallback_title}. AI analysis was not available at upload time."
            )

    async def analyze_image_from_url(
        self,
        image_url: str,
        fallback_title: str = "Untitled Image"
    ) -> ImageMetadata:
        """Analyze an image from a URL using Vision API.

        Args:
            image_url: Public URL to the image
            fallback_title: Title to use if analysis fails

        Returns:
            ImageMetadata with extracted metadata

        Raises:
            Exception: If analysis fails
        """
        try:
            # Call Vision API directly with URL
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this image and provide the structured metadata."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                response_format=ImageMetadata,
                temperature=0.3,
                max_tokens=500,
            )

            metadata = completion.choices[0].message.parsed

            # Validate and enforce limits (same as analyze_image)
            if not metadata.title or not metadata.short_description or not metadata.detailed_description:
                raise ValueError("Generated metadata is incomplete")

            if len(metadata.short_description) > 150:
                metadata.short_description = metadata.short_description[:147] + "..."

            if len(metadata.detailed_description) > 500:
                metadata.detailed_description = metadata.detailed_description[:497] + "..."

            logger.info(f"Analyzed image from URL - Title: '{metadata.title}'")

            return metadata

        except Exception as e:
            logger.error(f"Vision analysis from URL failed: {e}")
            return ImageMetadata(
                title=fallback_title,
                short_description=f"Image from URL: {fallback_title}",
                detailed_description=f"An image from URL. AI analysis was not available at upload time."
            )


# Global service instance
vision_analysis_service = VisionAnalysisService()
