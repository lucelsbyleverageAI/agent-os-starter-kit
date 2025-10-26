"""Docling converter service for managing document conversion configurations."""

import logging
from typing import Dict, Optional, Any
from pathlib import Path
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from docling.document_converter import DocumentConverter, ConversionResult, PdfFormatOption
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import TableItem

from langconnect.models.job import ProcessingOptions

logger = logging.getLogger(__name__)


class DoclingConversionError(Exception):
    """Custom exception for Docling conversion errors."""
    pass


class DoclingTimeoutError(DoclingConversionError):
    """Exception raised when conversion exceeds timeout."""
    pass


class DoclingConverterService:
    """Service for managing Docling DocumentConverter instances with different configurations."""
    
    def __init__(self):
        """Initialize the converter service."""
        logger.info("🔧 Initializing DoclingConverterService...")
        self.converters: Dict[str, DocumentConverter] = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="docling-worker")
        self._model_cache_dir = Path("models/cache")
        self._model_cache_dir.mkdir(parents=True, exist_ok=True)

        # Check if HuggingFace cache exists
        import os
        hf_home = os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))
        if Path(hf_home).exists():
            logger.info(f"✅ HuggingFace cache found at: {hf_home}")
        else:
            logger.warning(f"⚠️  HuggingFace cache not found at: {hf_home} - models will be downloaded on first use")

        logger.info("✅ DoclingConverterService initialized successfully")
        
    def get_converter(self, processing_mode: str) -> DocumentConverter:
        """Get or create a DocumentConverter for the specified processing mode.
        
        Args:
            processing_mode: Processing mode ('fast', 'balanced', 'enhanced')
            
        Returns:
            Configured DocumentConverter instance
        """
        if processing_mode not in self.converters:
            self.converters[processing_mode] = self._create_converter(processing_mode)
        
        return self.converters[processing_mode]
    
    def _create_converter(self, processing_mode: str) -> DocumentConverter:
        """Create a DocumentConverter with mode-specific configuration.

        Args:
            processing_mode: Processing mode to configure for

        Returns:
            Configured DocumentConverter
        """
        logger.info(f"🔨 Creating Docling converter for mode: {processing_mode}")
        start_time = time.time()

        # Configure pipeline options based on processing mode
        if processing_mode == "fast":
            pipeline_options = self._get_fast_pipeline_options()
            logger.info("📋 Using FAST mode: Text extraction + table detection")
        elif processing_mode == "balanced":
            pipeline_options = self._get_balanced_pipeline_options()
            logger.info("📋 Using BALANCED mode: Text extraction + table detection (no OCR)")
        elif processing_mode == "enhanced":
            pipeline_options = self._get_enhanced_pipeline_options()
            logger.info("📋 Using ENHANCED mode: Text extraction + table detection (no OCR)")
        else:
            logger.warning(f"⚠️  Unknown processing mode: {processing_mode}, using balanced")
            pipeline_options = self._get_balanced_pipeline_options()

        try:
            logger.info("⏳ Initializing DocumentConverter (may download models if not cached)...")
            # Create converter with configured options using the correct API structure
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )

            elapsed_time = time.time() - start_time
            logger.info(f"✅ Converter created successfully in {elapsed_time:.2f}s for mode: {processing_mode}")
            return converter

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ Failed to create converter after {elapsed_time:.2f}s: {e}", exc_info=True)

            # Provide specific error guidance
            if "SSL" in str(e) or "CERTIFICATE" in str(e):
                logger.error("💡 SSL certificate error - models may not be downloadable. Check network/certificates.")
            elif "Connection" in str(e) or "timeout" in str(e).lower():
                logger.error("💡 Network connection error - cannot download models from HuggingFace.")

            raise DoclingConversionError(f"Failed to create Docling converter: {str(e)}") from e
    
    def _get_fast_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for fast processing mode."""
        return PdfPipelineOptions(
            # Fast mode: speed-optimized with table extraction, no OCR
            do_ocr=False,  # Skip OCR for speed
            do_table_structure=True,  # Include table detection
            do_picture_description=False  # Skip detailed image analysis
        )
    
    def _get_balanced_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for balanced processing mode."""
        return PdfPipelineOptions(
            # Balanced mode: good quality text extraction with table detection, no OCR
            do_ocr=False,  # Skip OCR (use native PDF text extraction)
            do_table_structure=True,  # Include table detection
            do_picture_description=False  # Skip image analysis
        )
    
    def _get_enhanced_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for enhanced processing mode."""
        return PdfPipelineOptions(
            # Enhanced mode: highest quality text extraction with table detection, no OCR
            do_ocr=False,  # Skip OCR (use native PDF text extraction)
            do_table_structure=True,  # Advanced table detection
            do_picture_description=False  # Skip image analysis (not needed for text extraction)
        )
    
    async def convert_document(
        self,
        source_path: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        timeout: int = 300
    ) -> ConversionResult:
        """Convert a document using the specified processing options.

        Args:
            source_path: Path to the source document
            processing_options: Processing configuration
            progress_callback: Optional callback for progress updates
            timeout: Maximum time in seconds to wait for conversion (default: 300s = 5 minutes)

        Returns:
            ConversionResult from Docling

        Raises:
            DoclingTimeoutError: If conversion exceeds timeout
            DoclingConversionError: If conversion fails
        """
        import os
        file_size_mb = os.path.getsize(source_path) / (1024 * 1024) if os.path.exists(source_path) else 0
        logger.info(f"📄 Starting document conversion: {source_path} ({file_size_mb:.2f} MB)")
        logger.info(f"⚙️  Mode: {processing_options.processing_mode}, Timeout: {timeout}s")

        converter = self.get_converter(processing_options.processing_mode)

        if progress_callback:
            progress_callback("Starting document conversion")

        start_time = time.time()

        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            logger.info("⏳ Running conversion in thread pool executor...")

            # Use wait_for to enforce timeout
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self._convert_sync,
                    converter,
                    source_path
                ),
                timeout=timeout
            )

            elapsed_time = time.time() - start_time
            logger.info(f"✅ Conversion completed in {elapsed_time:.2f}s")

            if progress_callback:
                if result.status == ConversionStatus.SUCCESS:
                    progress_callback("Document conversion completed successfully")
                else:
                    progress_callback(f"Document conversion failed: {result.status}")

            # Log conversion details
            if result.status == ConversionStatus.SUCCESS:
                page_count = len(result.document.pages) if result.document else 0
                logger.info(f"📊 Conversion success: {page_count} pages processed")
            else:
                logger.warning(f"⚠️  Conversion status: {result.status}")

            return result

        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"Document conversion timed out after {elapsed_time:.2f}s (limit: {timeout}s)"
            logger.error(f"⏰ {error_msg}")
            if progress_callback:
                progress_callback(f"Timeout: {error_msg}")
            raise DoclingTimeoutError(error_msg)

        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"Error converting document {source_path} after {elapsed_time:.2f}s: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)

            if progress_callback:
                progress_callback(f"Conversion error: {str(e)}")

            # Provide specific error guidance
            if "SSL" in str(e) or "CERTIFICATE" in str(e):
                logger.error("💡 Try: export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt")
            elif "memory" in str(e).lower():
                logger.error("💡 Document too large - consider splitting or using fast mode")

            raise DoclingConversionError(error_msg) from e
    
    def _convert_sync(self, converter: DocumentConverter, source_path: str) -> ConversionResult:
        """Synchronous document conversion (runs in thread pool)."""
        return converter.convert(source_path)
    
    async def convert_url(
        self,
        url: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        timeout: int = 300
    ) -> ConversionResult:
        """Convert content from a URL using Docling.

        Args:
            url: URL to convert
            processing_options: Processing configuration
            progress_callback: Optional callback for progress updates
            timeout: Maximum time in seconds to wait for conversion (default: 300s = 5 minutes)

        Returns:
            ConversionResult from Docling

        Raises:
            DoclingTimeoutError: If conversion exceeds timeout
            DoclingConversionError: If conversion fails
        """
        logger.info(f"🌐 Starting URL conversion: {url}")
        logger.info(f"⚙️  Mode: {processing_options.processing_mode}, Timeout: {timeout}s")

        converter = self.get_converter(processing_options.processing_mode)

        if progress_callback:
            progress_callback(f"Starting URL conversion: {url}")

        start_time = time.time()

        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            logger.info("⏳ Running URL conversion in thread pool executor...")

            # Use wait_for to enforce timeout
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self._convert_url_sync,
                    converter,
                    url
                ),
                timeout=timeout
            )

            elapsed_time = time.time() - start_time
            logger.info(f"✅ URL conversion completed in {elapsed_time:.2f}s")

            if progress_callback:
                if result.status == ConversionStatus.SUCCESS:
                    progress_callback("URL conversion completed successfully")
                else:
                    progress_callback(f"URL conversion failed: {result.status}")

            # Log conversion details
            if result.status == ConversionStatus.SUCCESS:
                page_count = len(result.document.pages) if result.document else 0
                logger.info(f"📊 URL conversion success: {page_count} pages processed")
            else:
                logger.warning(f"⚠️  URL conversion status: {result.status}")

            return result

        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"URL conversion timed out after {elapsed_time:.2f}s (limit: {timeout}s)"
            logger.error(f"⏰ {error_msg}")
            if progress_callback:
                progress_callback(f"Timeout: {error_msg}")
            raise DoclingTimeoutError(error_msg)

        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"Error converting URL {url} after {elapsed_time:.2f}s: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)

            if progress_callback:
                progress_callback(f"URL conversion error: {str(e)}")

            # Provide specific error guidance
            if "SSL" in str(e) or "CERTIFICATE" in str(e):
                logger.error("💡 SSL certificate error accessing URL")
            elif "Connection" in str(e) or "timeout" in str(e).lower():
                logger.error("💡 Network connection error - cannot reach URL")

            raise DoclingConversionError(error_msg) from e
    
    def _convert_url_sync(self, converter: DocumentConverter, url: str) -> ConversionResult:
        """Synchronous URL conversion (runs in thread pool)."""
        return converter.convert(url)
    
    def extract_content_metadata(self, result: ConversionResult) -> Dict[str, Any]:
        """Extract metadata from a conversion result.
        
        Args:
            result: ConversionResult from Docling
            
        Returns:
            Dictionary of extracted metadata
        """
        metadata = {
            "conversion_status": result.status.value,
            "page_count": len(result.document.pages) if result.document else 0,
            "processing_time": getattr(result, 'processing_time', None),
        }
        
        if result.document:
            # Count different content types
            tables = []
            pictures = []
            
            try:
                for page in result.document.pages:
                    # Check if page has predictions attribute and is not None
                    if hasattr(page, 'predictions') and page.predictions is not None:
                        for item in page.predictions:
                            if isinstance(item, TableItem):
                                tables.append({
                                    "page": getattr(page, 'page_no', 0),
                                    "bbox": item.bbox.model_dump() if hasattr(item, 'bbox') and item.bbox else None
                                })
                    # Only log warning for unexpected page types, not missing predictions
                    elif not hasattr(page, 'predictions') and not isinstance(page, (int, str)):
                        logger.debug(f"Page object type {type(page)} does not have predictions attribute - this is normal for some document types")

            except Exception as e:
                logger.warning(f"Error extracting content metadata: {e}")
                # Continue with basic metadata even if detailed extraction fails
            
            metadata.update({
                "tables_found": len(tables),
                "pictures_found": len(pictures),
                "tables": tables,
                "pictures": pictures,
            })
        
        return metadata
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up Docling converter service")
        self.executor.shutdown(wait=True)
        self.converters.clear() 