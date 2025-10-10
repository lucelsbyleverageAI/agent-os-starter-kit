"""AI-powered metadata generation service for documents using OpenAI."""

import logging
import os
from typing import List
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Configuration
MAX_WORDS = int(os.getenv("AI_METADATA_MAX_WORDS", "10000"))
AI_MODEL = os.getenv("AI_METADATA_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """You are a document cataloging assistant for an AI-powered knowledge base.
Your task is to generate a concise, descriptive name and brief summary for documents that will help AI agents quickly identify relevant content.

Rules:
- Name: Clear, specific title (5-10 words max, no file extensions or special characters)
- Description: 1-2 sentences explaining what the document contains and its purpose (max 200 characters)
- Focus on key topics, themes, and actionable information
- Optimize for semantic search and agent comprehension
- Use professional, clear language

Examples:
- Good name: "Project Alpha Q4 Budget Report"
- Bad name: "document_final_v2.pdf"
- Good description: "Quarterly budget allocation and expense tracking for Project Alpha, including forecasts and variance analysis."
- Bad description: "This is a document about budgets."
"""


class DocumentMetadata(BaseModel):
    """Structured metadata for a document."""
    name: str = Field(..., description="Concise, descriptive title for the document (5-10 words, no file extensions)")
    description: str = Field(..., description="1-2 sentence summary of the document's content and purpose (max 200 characters)")


class AIMetadataService:
    """Service for generating AI-powered document metadata."""

    def __init__(self):
        """Initialize the AI metadata service."""
        self.client = AsyncOpenAI()
        self.max_words = MAX_WORDS
        self.model = AI_MODEL

    def truncate_content(self, text: str) -> str:
        """Truncate content to maximum word count for AI processing.

        Args:
            text: Full document content

        Returns:
            Truncated content with ellipsis if needed
        """
        words = text.split()
        if len(words) > self.max_words:
            truncated = ' '.join(words[:self.max_words])
            return f"{truncated}\n\n[Document continues beyond {self.max_words} words...]"
        return text

    async def generate_metadata(
        self,
        content: str,
        fallback_name: str = "Untitled Document"
    ) -> DocumentMetadata:
        """Generate metadata for a single document using OpenAI.

        Args:
            content: Full document content
            fallback_name: Name to use if AI generation fails

        Returns:
            DocumentMetadata with generated name and description
        """
        try:
            # Truncate content to avoid token limits
            truncated_content = self.truncate_content(content)

            # Generate metadata with structured output
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document content:\n\n{truncated_content}"}
                ],
                response_format=DocumentMetadata,
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=200,  # Limit output tokens for cost control
            )

            metadata = completion.choices[0].message.parsed

            # Validate metadata
            if not metadata.name or not metadata.description:
                raise ValueError("Generated metadata is incomplete")

            # Ensure description doesn't exceed 200 characters
            if len(metadata.description) > 200:
                metadata.description = metadata.description[:197] + "..."

            logger.info(f"Generated AI metadata - Name: '{metadata.name}', Description: '{metadata.description[:50]}...'")
            return metadata

        except Exception as e:
            logger.warning(f"AI metadata generation failed: {e}. Using fallback name.")
            # Return fallback metadata
            return DocumentMetadata(
                name=fallback_name,
                description=f"Content extracted from {fallback_name}."
            )

    async def generate_batch_metadata(
        self,
        contents: List[str],
        fallback_names: List[str] = None
    ) -> List[DocumentMetadata]:
        """Generate metadata for multiple documents in parallel.

        Args:
            contents: List of document contents
            fallback_names: List of fallback names if AI generation fails

        Returns:
            List of DocumentMetadata objects
        """
        if fallback_names is None:
            fallback_names = [f"Document {i+1}" for i in range(len(contents))]

        if len(fallback_names) != len(contents):
            raise ValueError("Number of fallback names must match number of contents")

        # Import asyncio for parallel processing
        import asyncio

        # Create tasks for parallel processing
        tasks = [
            self.generate_metadata(content, fallback)
            for content, fallback in zip(contents, fallback_names)
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks)

        logger.info(f"Generated metadata for {len(results)} documents in parallel")
        return results


# Global service instance
ai_metadata_service = AIMetadataService()
