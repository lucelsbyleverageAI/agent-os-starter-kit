"""Docling converter service for managing document conversion configurations."""

import logging
from typing import Dict, Optional, Any
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from docling.document_converter import DocumentConverter, ConversionResult, PdfFormatOption
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
from docling_core.types.doc import PictureItem, TableItem

from langconnect.models.job import ProcessingOptions

logger = logging.getLogger(__name__)


class DoclingConverterService:
    """Service for managing Docling DocumentConverter instances with different configurations."""
    
    def __init__(self):
        """Initialize the converter service."""
        self.converters: Dict[str, DocumentConverter] = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="docling-worker")
        self._model_cache_dir = Path("models/cache")
        self._model_cache_dir.mkdir(parents=True, exist_ok=True)
        
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
        logger.info(f"Creating Docling converter for mode: {processing_mode}")
        
        # Configure pipeline options based on processing mode
        if processing_mode == "fast":
            pipeline_options = self._get_fast_pipeline_options()
        elif processing_mode == "balanced":
            pipeline_options = self._get_balanced_pipeline_options()
        elif processing_mode == "enhanced":
            pipeline_options = self._get_enhanced_pipeline_options()
        else:
            logger.warning(f"Unknown processing mode: {processing_mode}, using balanced")
            pipeline_options = self._get_balanced_pipeline_options()
        
        # Create converter with configured options using the correct API structure
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        
        logger.info(f"Created converter for mode: {processing_mode}")
        return converter
    
    def _get_fast_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for fast processing mode."""
        return PdfPipelineOptions(
            # Fast mode: speed-optimized with table extraction
            do_ocr=False,  # Skip OCR for speed
            do_table_structure=True,  # Include table detection (NEW)
            do_picture_analysis=False,  # Skip detailed image analysis
            ocr_options=EasyOcrOptions(force_full_page_ocr=False)
        )
    
    def _get_balanced_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for balanced processing mode."""
        return PdfPipelineOptions(
            # Balanced mode: good quality with reasonable speed
            do_ocr=True,  # Enable OCR
            do_table_structure=True,  # Table detection
            do_picture_analysis=False,  # Skip image analysis for speed (CHANGED)
            ocr_options=EasyOcrOptions(
                force_full_page_ocr=False,
                lang=["en"]  # English OCR
            )
        )
    
    def _get_enhanced_pipeline_options(self) -> PdfPipelineOptions:
        """Get pipeline options for enhanced processing mode."""
        return PdfPipelineOptions(
            # Enhanced mode: maximum quality processing
            do_ocr=True,  # Full OCR processing
            do_table_structure=True,  # Advanced table detection
            do_picture_analysis=True,  # Full image analysis
            ocr_options=EasyOcrOptions(
                force_full_page_ocr=True,  # Full page OCR
                lang=["en", "es", "fr", "de"]  # Multi-language support
            )
        )
    
    async def convert_document(
        self, 
        source_path: str, 
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """Convert a document using the specified processing options.
        
        Args:
            source_path: Path to the source document
            processing_options: Processing configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            ConversionResult from Docling
        """
        converter = self.get_converter(processing_options.processing_mode)
        
        if progress_callback:
            progress_callback("Starting document conversion")
        
        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, 
                self._convert_sync, 
                converter, 
                source_path
            )
            
            if progress_callback:
                if result.status == ConversionStatus.SUCCESS:
                    progress_callback("Document conversion completed successfully")
                else:
                    progress_callback(f"Document conversion failed: {result.status}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error converting document {source_path}: {e}")
            if progress_callback:
                progress_callback(f"Conversion error: {str(e)}")
            raise
    
    def _convert_sync(self, converter: DocumentConverter, source_path: str) -> ConversionResult:
        """Synchronous document conversion (runs in thread pool)."""
        return converter.convert(source_path)
    
    async def convert_url(
        self, 
        url: str, 
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """Convert content from a URL using Docling.
        
        Args:
            url: URL to convert
            processing_options: Processing configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            ConversionResult from Docling
        """
        converter = self.get_converter(processing_options.processing_mode)
        
        if progress_callback:
            progress_callback(f"Starting URL conversion: {url}")
        
        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, 
                self._convert_url_sync, 
                converter, 
                url
            )
            
            if progress_callback:
                if result.status == ConversionStatus.SUCCESS:
                    progress_callback("URL conversion completed successfully")
                else:
                    progress_callback(f"URL conversion failed: {result.status}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error converting URL {url}: {e}")
            if progress_callback:
                progress_callback(f"URL conversion error: {str(e)}")
            raise
    
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
                            elif isinstance(item, PictureItem):
                                pictures.append({
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