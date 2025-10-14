import { useState, Dispatch, SetStateAction, useCallback, useRef, useEffect } from "react";
import { Document } from "@langchain/core/documents";
import { Collection, CollectionCreate } from "@/types/collection";
import { ShareAtCreation } from "@/types/user";
import { notify } from "@/utils/toast";
import { knowledgeMessages } from "@/utils/toast-messages";
import { toast } from "sonner";
import { useAuthContext } from "@/providers/Auth";
import { useJobTracking, ProcessingJob, JobStatus } from "@/hooks/use-job-tracking";
import type { UploadData, ProcessingMode } from "../components/enhanced-upload-dialog";

export const DEFAULT_COLLECTION_NAME = "default_collection";

// ✅ PHASE 1: Enhanced Collections Cache Configuration
const COLLECTIONS_CACHE_KEY = 'oap_collections_cache_v2';
const COLLECTIONS_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const _DOCUMENT_COUNTS_CACHE_DURATION = 2 * 60 * 1000; // 2 minutes (more frequent updates)
const _COLLECTION_STATS_CACHE_DURATION = 10 * 60 * 1000; // 10 minutes

// ✅ PHASE 2: Document List Cache Configuration
const DOCUMENT_LIST_CACHE_KEY_PREFIX = 'oap_documents_';
const DOCUMENT_LIST_CACHE_DURATION = 3 * 60 * 1000; // 3 minutes
const DOCUMENT_SEARCH_CACHE_KEY_PREFIX = 'oap_doc_search_';
const _DOCUMENT_SEARCH_CACHE_DURATION = 2 * 60 * 1000; // 2 minutes

// ✅ PHASE 1: Enhanced Collections Cache Structure
interface EnhancedCollectionsCache {
  collections: Collection[];
  documentCounts: Record<string, number>;
  collectionStats: Record<string, CollectionStats>;
  timestamp: number;
  version: number;
  staleAfter: number;
  lastRefresh: number;
  userId: string;
}

interface CollectionStats {
  document_count: number;
  total_chunks: number;
  total_size: number;
  last_updated: string;
  timestamp: number;
}

// ✅ PHASE 2: Document List Cache Structure
interface DocumentListCache {
  documents: Document[];
  totalCount: number;
  currentOffset: number;
  hasMore: boolean;
  timestamp: number;
  collectionId: string;
  limit: number;
  searchQuery?: string;
}

// ✅ PHASE 2: Document Search Cache Structure
interface DocumentSearchCache {
  [collectionId: string]: {
    [searchQuery: string]: {
      results: Document[];
      totalMatches: number;
      timestamp: number;
    }
  }
}

// ✅ PHASE 1: Cache Invalidation Events
enum CollectionCacheEvent {
  COLLECTION_CREATED = 'collection_created',
  COLLECTION_UPDATED = 'collection_updated',
  COLLECTION_DELETED = 'collection_deleted',
  DOCUMENT_UPLOADED = 'document_uploaded',
  DOCUMENT_DELETED = 'document_deleted',
  BATCH_DOCUMENTS_PROCESSED = 'batch_documents_processed',
  PERMISSION_CHANGED = 'permission_changed'
}

export function getDefaultCollection(collections: Collection[]): Collection {
  return (
    collections.find((c) => c.name === DEFAULT_COLLECTION_NAME) ??
    collections[0]
  );
}

// API calls now use the Next.js proxy route at /api/langconnect/

export function getCollectionName(name: string | undefined) {
  if (!name) return "";
  return name === DEFAULT_COLLECTION_NAME ? "Default" : name;
}

/**
 * Enhanced upload function using the new batch processing endpoint
 */
// Helper functions for intelligent naming
function generateBatchTitle(uploadData: UploadData, itemCount: number): string {
  if (itemCount === 1) {
    if (uploadData.files.length === 1) return uploadData.files[0].name;
    if (uploadData.urls.length === 1) return `Import: ${uploadData.urls[0].url}`;
    if (uploadData.textContent) return `Text: ${uploadData.textContent.substring(0, 30)}...`;
  }
  
  const parts: string[] = [];
  if (uploadData.files.length > 0) parts.push(`${uploadData.files.length} files`);
  if (uploadData.urls.length > 0) parts.push(`${uploadData.urls.length} URLs`);
  if (uploadData.textContent) parts.push('text content');
  
  return `Batch upload: ${parts.join(', ')}`;
}

// function generateBatchDescription(uploadData: UploadData): string {
//   const details: string[] = [];
  
//   if (uploadData.files.length > 0) {
//     details.push(`Files: ${uploadData.files.map(f => f.name).join(', ')}`);
//   }
  
//   if (uploadData.urls.length > 0) {
//     details.push(`URLs: ${uploadData.urls.map(u => u.url).join(', ')}`);
//   }
  
//   if (uploadData.textContent) {
//     details.push(`Text content (${uploadData.textContent.length} characters)`);
//   }
  
//   return `Batch processed with ${uploadData.processingMode} mode. ${details.join(' | ')}`;
// }

function generateBatchDescription(uploadData: UploadData): string {
  const details: string[] = [];
  
  if (uploadData.files.length > 0) {
    details.push(`Files: ${uploadData.files.map(f => f.name).join(', ')}`);
  }
  
  if (uploadData.urls.length > 0) {
    details.push(`URLs: ${uploadData.urls.map(u => u.url).join(', ')}`);
  }
  
  if (uploadData.textContent) {
    details.push(`Text content (${uploadData.textContent.length} characters)`);
  }
  
  return ``;
}

async function uploadDocumentsEnhanced(
  collectionId: string,
  uploadData: UploadData,
  authorization: string,
): Promise<{ job_id: string; status: string; message: string }> {
  const url = `/api/langconnect/collections/${encodeURIComponent(collectionId)}/documents`;
  
  try {
    // Create single FormData with all content
    const formData = new FormData();
    
    // Add all files to single request
    uploadData.files.forEach(file => {
      formData.append("files", file, file.name);
    });
    
    // Add all URLs as comma-separated string
    if (uploadData.urls.length > 0) {
      const urlString = uploadData.urls.map(item => item.url).join(',');
      formData.append("urls", urlString);
    }
    
    // Add text content
    if (uploadData.textContent.trim()) {
      formData.append("text_content", uploadData.textContent.trim());
    }
    
    // Add processing configuration
    formData.append("processing_mode", uploadData.processingMode);
    formData.append("use_ai_metadata", uploadData.useAIMetadata.toString());

    // Generate job-level metadata (for tracking the batch)
    const itemCount = uploadData.files.length + uploadData.urls.length + (uploadData.textContent ? 1 : 0);
    formData.append("job_title", generateBatchTitle(uploadData, itemCount));
    formData.append("job_description", generateBatchDescription(uploadData));
    
    // For individual documents, let the backend generate appropriate titles/descriptions
    // based on the actual file content and characteristics
    
    // Single HTTP request for entire batch
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      headers: {
        Authorization: `Bearer ${authorization}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Upload failed: ${errorData.detail || response.statusText}`);
    }

    // Returns single job ID instead of array
    return await response.json();
    
  } catch (error) {
    console.error("Batch upload error:", error);
    throw error;
  }
}

// --- Type Definitions ---

// Return type for the combined hook
interface UseKnowledgeReturn {
  // Misc
  initialSearchExecuted: boolean;
  setInitialSearchExecuted: Dispatch<SetStateAction<boolean>>;
  // Initial load
  initialFetch: (accessToken: string) => Promise<void>;

  // Collection state and operations
  collections: Collection[];
  setCollections: Dispatch<SetStateAction<Collection[]>>;
  collectionsLoading: boolean;
  setCollectionsLoading: Dispatch<SetStateAction<boolean>>;
  getCollections: (accessToken?: string, useCache?: boolean) => Promise<Collection[]>;
  createCollection: (
    name: string,
    metadata?: Record<string, any>,
    accessToken?: string,
  ) => Promise<Collection | undefined>;
  createCollectionWithSharing: (
    name: string,
    metadata: Record<string, any>,
    shareWith?: ShareAtCreation[],
    accessToken?: string,
  ) => Promise<Collection | undefined>;
  updateCollection: (
    collectionId: string,
    newName: string,
    metadata: Record<string, any>,
  ) => Promise<Collection | undefined>;
  deleteCollection: (collectionId: string) => Promise<{ ok: true } | { ok: false; errorMessage: string }>;
  refreshCollectionDocumentCount: (collectionId: string) => Promise<void>;

  // Selected collection
  selectedCollection: Collection | undefined;
  setSelectedCollection: Dispatch<SetStateAction<Collection | undefined>>;

  // Document state and operations
  documents: Document[];
  setDocuments: Dispatch<SetStateAction<Document[]>>;
  documentsLoading: boolean;
  setDocumentsLoading: Dispatch<SetStateAction<boolean>>;
  listDocuments: (
    collectionId: string,
    args?: { limit?: number; offset?: number; useCache?: boolean; searchQuery?: string },
    accessToken?: string,
  ) => Promise<Document[]>;
  deleteDocument: (id: string, documentName?: string, collectionId?: string) => Promise<void>;
  
  // Enhanced upload functions
  handleEnhancedUpload: (
    uploadData: UploadData,
    collectionId: string,
  ) => Promise<void>;
  
  // Legacy upload functions (deprecated but kept for compatibility)
  handleFileUpload: (
    files: FileList | null,
    collectionId: string,
  ) => Promise<void>;
  handleTextUpload: (textInput: string, collectionId: string) => Promise<void>;

  // Job tracking integration
  processingJobs: ProcessingJob[];
  getJobsByCollection: (collectionId: string) => ProcessingJob[];
  activeJobsCount: number;
  cancelJob: (jobId: string) => Promise<boolean>;
}

/**
 * Custom hook for managing Knowledge collections and documents.
 * Now includes enhanced upload capabilities and job tracking.
 */
export function useKnowledge(): UseKnowledgeReturn {
  const { session } = useAuthContext();
  
  // --- State ---
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collectionsLoading, setCollectionsLoading] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<
    Collection | undefined
  >(undefined);
  const [initialSearchExecuted, setInitialSearchExecuted] = useState(false);

  // Listen for cache invalidation events from notifications
  useEffect(() => {
    const handleCacheInvalidation = async (event: any) => {
      if (session?.accessToken) {
        try {
          // Clear cache and trigger a re-fetch
          if (typeof window !== 'undefined') {
            const cacheKeys = Object.keys(localStorage).filter(key => 
              key.includes('oap_collections_cache')
            );
            cacheKeys.forEach(key => localStorage.removeItem(key));
          }
          
          // Trigger a direct API call to refresh collections
          const response = await fetch('/api/langconnect/collections', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          });
          
          if (response.ok) {
            const refreshedCollections = await response.json();
            setCollections(refreshedCollections);
          }
        } catch (_error) {
          // Failed to refresh collections after cache invalidation
        }
      }
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('collections-cache-invalidated', handleCacheInvalidation);
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('collections-cache-invalidated', handleCacheInvalidation);
      }
    };
  }, [session?.accessToken]);

  // --- Initial Fetch ---
  const initialFetch = useCallback(async (accessToken: string) => {
    setCollectionsLoading(true);
    setDocumentsLoading(true);
    let initCollections: Collection[] = [];

    try {
      initCollections = await getCollections(accessToken);
    } catch (e: any) {
      if (e.message.includes("Failed to fetch collections")) {
        // Database likely not initialized yet. Let's try this then re-fetch.
        await initializeDatabase(accessToken);
        initCollections = await getCollections(accessToken);
      }
    }

    if (!initCollections.length) {
      // No collections exist, return early
      setCollectionsLoading(false);
      setDocumentsLoading(false);
      setInitialSearchExecuted(true);
      return;
    }

    setCollections(initCollections);
    const defaultCollection = initCollections[0];
    setSelectedCollection(defaultCollection);

    setInitialSearchExecuted(true);
    setCollectionsLoading(false);

    const documents = await listDocuments(
      defaultCollection.uuid,
      {
        limit: 100,
      },
      accessToken,
    );
    setDocuments(documents);
    setDocumentsLoading(false);
  }, []); // Dependencies removed - functions are used via closure

  const initializeDatabase = useCallback(
    async (accessToken?: string) => {
      if (!session?.accessToken && !accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to list documents. Please try again.",
        });
        return [];
      }

      const response = await fetch("/api/langconnect/admin/initialize-database", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken || session?.accessToken}`,
        },
      });
      if (!response.ok) {
        throw new Error(
          `Failed to initialize database: ${response.statusText}`,
        );
      }
      const data = await response.json();
      return data;
    },
    [session],
  );

  // --- Document Operations ---

  const listDocuments = useCallback(
    async (
      collectionId: string,
      args?: { limit?: number; offset?: number; useCache?: boolean; searchQuery?: string },
      accessToken?: string,
    ): Promise<Document[]> => {
      const startTime = Date.now();
      const limit = args?.limit || 20;
      const offset = args?.offset || 0;
      const useCache = args?.useCache !== false; // Default to true
      const searchQuery = args?.searchQuery;
      
      // ✅ PHASE 2: Document List Cache Check
      if (useCache && offset === 0) { // Only use cache for first page requests
        const cachedData = getDocumentListCache(collectionId, searchQuery);
        if (cachedData && cachedData.limit >= limit) {
          
          // Return slice of cached documents for pagination
          const endIndex = Math.min(limit, cachedData.documents.length);
          return cachedData.documents.slice(0, endIndex);
        }
      }
      
      if (!session?.accessToken && !accessToken) {
        const error = new Error("No session found");
        toast.error("No session found", {
          richColors: true,
          description: "Failed to list documents. Please try again.",
        });
        throw error;
      }

      
      const url = new URL(`/api/langconnect/collections/${collectionId}/documents`, window.location.origin);
      url.searchParams.set("limit", limit.toString());
      url.searchParams.set("offset", offset.toString());
      
      if (searchQuery) {
        url.searchParams.set("search", searchQuery);
      }

      const response = await fetch(url.toString(), {
        headers: {
          Authorization: `Bearer ${accessToken || session?.accessToken}`,
        },
      });
      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.statusText}`);
      }
      const data = await response.json();
      
      // Convert new document format to legacy Document format for compatibility
      const documents = data.documents.map((doc: any) => ({
        id: doc.id,
        pageContent: doc.content || "",
        metadata: {
          file_id: doc.id,
          name: doc.title,
          title: doc.title,
          description: doc.description,
          collection: collectionId,
          created_at: doc.created_at,
          updated_at: doc.updated_at,
          source_type: doc.source_type,
          chunk_count: doc.chunk_count,
          ...doc.metadata
        }
      }));
      
      const _fetchDuration = Date.now() - startTime;
      
      // ✅ PHASE 2: Cache the results (only for first page requests to keep cache simple)
      if (offset === 0 && documents.length > 0) {
        const totalCount = data.total_count || documents.length;
        const hasMore = documents.length >= limit && (offset + documents.length) < totalCount;
        
        setDocumentListCache(collectionId, {
          documents,
          totalCount,
          currentOffset: documents.length,
          hasMore,
          limit,
          searchQuery,
        });
        
        // ✅ PHASE 2: Also cache search results if this was a search
        if (searchQuery) {
          setDocumentSearchCache(collectionId, searchQuery, documents, totalCount);
        }
      }
      
      return documents;
    },
    [session],
  );

  // Function to refresh document count for a specific collection
  const refreshCollectionDocumentCount = useCallback(
    async (collectionId: string) => {
      if (!session?.accessToken) return;

      try {
        const statsResponse = await fetch(`/api/langconnect/collections/${collectionId}/stats`, {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });
        
        if (statsResponse.ok) {
          const stats = await statsResponse.json();
          const documentCount = stats.document_stats?.document_count || 0;
          
          // Update the specific collection in the collections array
          setCollections(prevCollections => 
            prevCollections.map(collection => 
              collection.uuid === collectionId 
                ? { ...collection, document_count: documentCount }
                : collection
            )
          );
        }
      } catch (error) {
        console.error(`Failed to refresh document count for collection ${collectionId}:`, error);
      }
    },
    [session]
  );

  // Create a callback for when jobs complete to refresh documents
  // Use a ref to debounce multiple rapid refreshes
  const refreshTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const handleJobCompleted = useCallback(async (job: ProcessingJob) => {
    
    // ✅ PHASE 1 & 2: Smart Cache Invalidation on Job Completion
    if (job.documents_processed > 0) {
      // Invalidate both collections cache (for document counts) and document list cache
      invalidateCollectionSpecific(job.collection_id, CollectionCacheEvent.BATCH_DOCUMENTS_PROCESSED);
    }
        
    // Only refresh if this is for the currently selected collection
    if (selectedCollection && selectedCollection.uuid === job.collection_id) {
      // Clear any existing timeout to debounce multiple rapid completions
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      
      // Schedule a debounced refresh after 500ms
      refreshTimeoutRef.current = setTimeout(async () => {
        try {
          
          // ✅ PHASE 2: Force fresh data by bypassing cache
          const refreshedDocuments = await listDocuments(job.collection_id, { useCache: false });
          setDocuments(refreshedDocuments);
          
                    
          // Also refresh the collection's document count badge
          await refreshCollectionDocumentCount(job.collection_id);
        } catch (error) {
          console.error('Failed to refresh documents after job completion:', error);
        }
      }, 500);
    } else {
      // Even if it's not the selected collection, refresh the document count badge
      await refreshCollectionDocumentCount(job.collection_id);
    }
  }, [selectedCollection, listDocuments, refreshCollectionDocumentCount]);

  const jobTracking = useJobTracking({
    onJobCompleted: handleJobCompleted
  });

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, []);

  const deleteDocument = useCallback(
    async (id: string, documentName?: string, collectionId?: string): Promise<void> => {
      if (!session?.accessToken) {
        const error = new Error("No session found");
        const message = knowledgeMessages.document.delete.error();
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
        throw error;
      }

      // Use provided collectionId or fall back to selectedCollection
      const targetCollectionId = collectionId || selectedCollection?.uuid;
      if (!targetCollectionId) {
        const error = new Error("No collection specified");
        toast.error("No collection specified", {
          richColors: true,
          description: "Please specify a collection for deletion.",
        });
        throw error;
      }

      // Find the document for additional info
      const documentToDelete = documents.find(doc => doc.metadata.file_id === id);
      const _docName = documentName || documentToDelete?.metadata.name || "Unknown document";

      const response = await fetch(`/api/langconnect/collections/${targetCollectionId}/documents/${id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });
      
      if (!response.ok) {
        let errorDetail = response.statusText;
        try {
          // Try to get more detailed error from response body
          const errorData = await response.json();
          errorDetail = errorData.detail || errorDetail;
        } catch (_) {
          // If we can't parse the JSON, stick with status text
        }
        
        const errorMessage = `Failed to delete document: ${errorDetail}`;
        console.error(errorMessage);
        throw new Error(errorMessage);
      }

      // Check the actual response body to see if deletion was successful
      let responseData;
      try {
        responseData = await response.json();
              } catch (error) {
        console.error("Failed to parse delete response:", error);
        throw new Error("Failed to parse server response");
      }

      if (!responseData.success) {
        const errorMessage = "Document deletion failed on server";
        console.error(errorMessage, responseData);
        throw new Error(errorMessage);
      }

      // Update local state to remove the deleted document
      setDocuments((prevDocs) =>
        prevDocs.filter((doc) => doc.metadata.file_id !== id),
      );

      // ✅ PHASE 1: Smart Cache Invalidation - Invalidate cache after successful deletion
      invalidateCollectionSpecific(targetCollectionId, CollectionCacheEvent.DOCUMENT_DELETED);

    },
    [selectedCollection, session, documents],
  );

  // --- Enhanced Upload Function ---
  const handleEnhancedUpload = useCallback(
    async (uploadData: UploadData, collectionId: string) => {
      if (!session?.accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to upload documents. Please try again.",
        });
        return;
      }

      try {
        const result = await uploadDocumentsEnhanced(
          collectionId,
          uploadData,
          session.accessToken,
        );

        // Create processing job object and add it to tracking
        const processingJob: ProcessingJob = {
          id: result.job_id,
          status: result.status as JobStatus,
          progress_percentage: 0,
          title: result.message,
          collection_id: collectionId,
          job_type: 'document_processing',
          created_at: new Date(),
          documents_processed: 0,
          chunks_created: 0,
          processing_mode: uploadData.processingMode,
        };

        jobTracking.addJob(processingJob);

        // ✅ Note: Cache invalidation will happen when job completes, not when it starts
        // This ensures we don't invalidate cache before documents are actually processed

        // Toast is now handled by the upload dialog component

      } catch (error) {
        console.error("Enhanced upload error:", error);
        throw error;
      }
    },
    [session, jobTracking],
  );

  // --- Legacy Upload Functions (for backward compatibility) ---
  const handleFileUpload = useCallback(
    async (files: FileList | null, collectionId: string) => {
      if (!files || files.length === 0) {
        console.warn("File upload skipped: No files selected.");
        return;
      }

      // Convert to enhanced upload format
      const uploadData: UploadData = {
        files: Array.from(files),
        urls: [],
        textContent: "",
        processingMode: "fast" as ProcessingMode,
        useAIMetadata: false,
      };

      await handleEnhancedUpload(uploadData, collectionId);
    },
    [handleEnhancedUpload],
  );

  const handleTextUpload = useCallback(
    async (textInput: string, collectionId: string) => {
      if (!textInput.trim()) {
        console.warn("Text upload skipped: Text is empty.");
        return;
      }

      // Convert to enhanced upload format
      const uploadData: UploadData = {
        files: [],
        urls: [],
        textContent: textInput,
        processingMode: "fast" as ProcessingMode,
        useAIMetadata: false,
      };

      await handleEnhancedUpload(uploadData, collectionId);
    },
    [handleEnhancedUpload],
  );

  // --- Cache Management ---

  const getCachedCollections = useCallback((): EnhancedCollectionsCache | null => {
    try {
      const cached = localStorage.getItem(COLLECTIONS_CACHE_KEY);
      if (cached) {
        const cacheData = JSON.parse(cached) as EnhancedCollectionsCache;
        if (Date.now() - cacheData.timestamp < COLLECTIONS_CACHE_DURATION) {
          return cacheData;
        }
      }
    } catch (e) {
      console.warn('Failed to read collections cache:', e);
    }
    return null;
  }, []);

  const setCachedCollections = useCallback((collections: Collection[]) => {
    try {
      const documentCounts: Record<string, number> = {};
      collections.forEach(c => {
        if (c.document_count !== undefined) {
          documentCounts[c.uuid] = c.document_count;
        }
      });

      const cacheData: EnhancedCollectionsCache = {
        collections,
        timestamp: Date.now(),
        documentCounts,
        collectionStats: {},
        version: 1,
        staleAfter: Date.now() + COLLECTIONS_CACHE_DURATION,
        lastRefresh: Date.now(),
                 userId: session?.user?.id || "",
      };
      localStorage.setItem(COLLECTIONS_CACHE_KEY, JSON.stringify(cacheData));
    } catch (e) {
      console.warn('Failed to cache collections:', e);
    }
  }, [session]);

  const invalidateCollectionsCache = useCallback(() => {
    try {
      localStorage.removeItem(COLLECTIONS_CACHE_KEY);
    } catch (e) {
      console.warn('Failed to invalidate collections cache:', e);
    }
  }, []);

  // ✅ PHASE 1: Enhanced Cache Management Functions
  const isCollectionsCacheStale = useCallback((cacheData: EnhancedCollectionsCache): boolean => {
    const now = Date.now();
    return now > cacheData.staleAfter;
  }, []);

  const getCollectionsFromCacheOrStale = useCallback((): { data: EnhancedCollectionsCache | null; isStale: boolean } => {
    const cached = getCachedCollections();
    if (!cached) return { data: null, isStale: false };
    
    const isStale = isCollectionsCacheStale(cached);
    return { data: cached, isStale };
  }, [getCachedCollections, isCollectionsCacheStale]);

  // ✅ PHASE 2: Document List Cache Management
  const getDocumentListCache = useCallback((collectionId: string, searchQuery?: string): DocumentListCache | null => {
    try {
      const cacheKey = `${DOCUMENT_LIST_CACHE_KEY_PREFIX}${collectionId}${searchQuery ? `_${searchQuery}` : ''}`;
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const cacheData = JSON.parse(cached) as DocumentListCache;
        if (Date.now() - cacheData.timestamp < DOCUMENT_LIST_CACHE_DURATION) {
          return cacheData;
        }
      }
    } catch (e) {
      console.warn('Failed to read document list cache:', e);
    }
    return null;
  }, []);

  const setDocumentListCache = useCallback((collectionId: string, data: Partial<DocumentListCache>) => {
    try {
      const cacheKey = `${DOCUMENT_LIST_CACHE_KEY_PREFIX}${collectionId}${data.searchQuery ? `_${data.searchQuery}` : ''}`;
      const cacheData: DocumentListCache = {
        documents: data.documents || [],
        totalCount: data.totalCount || 0,
        currentOffset: data.currentOffset || 0,
        hasMore: data.hasMore || false,
        timestamp: Date.now(),
        collectionId,
        limit: data.limit || 20,
        searchQuery: data.searchQuery,
      };
      localStorage.setItem(cacheKey, JSON.stringify(cacheData));
    } catch (e) {
      console.warn('Failed to cache document list:', e);
    }
  }, []);

  const invalidateDocumentListCache = useCallback((collectionId?: string) => {
    try {
      const keysToRemove: string[] = [];
      
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith(DOCUMENT_LIST_CACHE_KEY_PREFIX)) {
          if (!collectionId || key.includes(collectionId)) {
            keysToRemove.push(key);
          }
        }
      }
      
      keysToRemove.forEach(key => localStorage.removeItem(key));
    } catch (e) {
      console.warn('Failed to invalidate document list cache:', e);
    }
  }, []);



  const setDocumentSearchCache = useCallback((collectionId: string, searchQuery: string, results: Document[], totalMatches: number) => {
    try {
      const cacheKey = `${DOCUMENT_SEARCH_CACHE_KEY_PREFIX}${collectionId}`;
      const existing = localStorage.getItem(cacheKey);
      const cacheData: DocumentSearchCache = existing ? JSON.parse(existing) : {};
      
      if (!cacheData[collectionId]) {
        cacheData[collectionId] = {};
      }
      
      cacheData[collectionId][searchQuery] = {
        results,
        totalMatches,
        timestamp: Date.now(),
      };
      
      localStorage.setItem(cacheKey, JSON.stringify(cacheData));
    } catch (e) {
      console.warn('Failed to cache document search:', e);
    }
  }, []);

  // ✅ PHASE 1: Smart Cache Invalidation
  const invalidateCollectionSpecific = useCallback((collectionId: string, event: CollectionCacheEvent) => {
    try {
      const cached = getCachedCollections();
      if (!cached) return;

      let shouldInvalidateAll = false;
      let shouldInvalidateDocumentCounts = false;

      switch (event) {
        case CollectionCacheEvent.COLLECTION_CREATED:
        case CollectionCacheEvent.COLLECTION_DELETED:
        case CollectionCacheEvent.PERMISSION_CHANGED:
          shouldInvalidateAll = true;
          break;
        
        case CollectionCacheEvent.DOCUMENT_UPLOADED:
        case CollectionCacheEvent.DOCUMENT_DELETED:
        case CollectionCacheEvent.BATCH_DOCUMENTS_PROCESSED:
          shouldInvalidateDocumentCounts = true;
          break;
      }

      if (shouldInvalidateAll) {
        invalidateCollectionsCache();
        invalidateDocumentListCache(collectionId);
      } else if (shouldInvalidateDocumentCounts) {
        // Only invalidate document counts for this collection
        const updatedCache = { ...cached };
        delete updatedCache.documentCounts[collectionId];
        delete updatedCache.collectionStats[collectionId];
        localStorage.setItem(COLLECTIONS_CACHE_KEY, JSON.stringify(updatedCache));
        
        // Also invalidate document list cache for this collection
        invalidateDocumentListCache(collectionId);
      }
    } catch (e) {
      console.warn('Failed to invalidate collection specific cache:', e);
    }
  }, [getCachedCollections, invalidateCollectionsCache, invalidateDocumentListCache]);

  // --- Document Operations ---

  const getCollections = useCallback(
    async (accessToken?: string, useCache: boolean = true): Promise<Collection[]> => {
      const startTime = Date.now();
      
      // ✅ PHASE 1: Enhanced Cache Strategy with Stale-While-Revalidate
      if (useCache) {
        const { data: cachedData, isStale } = getCollectionsFromCacheOrStale();
        if (cachedData) {
          
          // If stale, trigger background refresh
          if (isStale) {
            setTimeout(() => {
              
              getCollections(accessToken, false);
            }, 0);
          }
          
          return cachedData.collections;
        }
      }
      
      if (!session?.accessToken && !accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to fetch collections. Please try again.",
        });
        return [];
      }

      const auth = `Bearer ${accessToken || session?.accessToken}`;
      
      
      const _collectionsStartTime = Date.now();

      // ✅ PHASE 1: Fetch collections list
      const response = await fetch("/api/langconnect/collections", {
        headers: { Authorization: auth },
      });
      if (!response.ok) {
        throw new Error(`Failed to fetch collections: ${response.statusText}`);
      }
      const collections = await response.json();
      
      
      
      // ✅ PHASE 1: Parallel Document Count Fetching (Key Performance Improvement)
      const statsStartTime = Date.now();
      
      // Create all fetch promises simultaneously for true parallelism
      const statsPromises = collections.map(async (collection: Collection) => {
        const statsStartTime = Date.now();
        
        try {
          const statsResponse = await fetch(`/api/langconnect/collections/${collection.uuid}/stats`, {
            headers: { Authorization: auth },
          });
          
          const _statsDuration = Date.now() - statsStartTime;
          
          if (statsResponse.ok) {
            const stats = await statsResponse.json();
            const documentCount = stats.document_stats?.document_count || 0;
            
            
            
            return {
              ...collection,
              document_count: documentCount,
              stats: {
                document_count: documentCount,
                total_chunks: stats.document_stats?.total_chunks || 0,
                total_size: stats.document_stats?.total_size || 0,
                last_updated: stats.document_stats?.last_updated || new Date().toISOString(),
                timestamp: Date.now(),
              },
            };
          } else {
            console.warn(`  ⚠️ Stats fetch failed for ${collection.name}: ${statsResponse.status}`);
            return {
              ...collection,
              document_count: 0,
              stats: {
                document_count: 0,
                total_chunks: 0,
                total_size: 0,
                last_updated: new Date().toISOString(),
                timestamp: Date.now(),
              },
            };
          }
        } catch (error) {
          console.error(`  ❌ Stats fetch error for ${collection.name}:`, error);
          return {
            ...collection,
            document_count: 0,
            stats: {
              document_count: 0,
              total_chunks: 0,
              total_size: 0,
              last_updated: new Date().toISOString(),
              timestamp: Date.now(),
            },
          };
        }
      });
      
      // Execute all stats fetches in parallel
      const collectionsWithStats = await Promise.all(statsPromises);
      
      const _statsTotalDuration = Date.now() - statsStartTime;
      const _totalDuration = Date.now() - startTime;
      
          
      
      // ✅ PHASE 1: Enhanced Cache Storage
      const collectionStats: Record<string, CollectionStats> = {};
      collectionsWithStats.forEach(collection => {
        if (collection.stats) {
          collectionStats[collection.uuid] = collection.stats;
        }
      });
      
      // Cache the results with enhanced metadata
      setCachedCollections(collectionsWithStats);
      
      return collectionsWithStats;
    },
    [session, getCollectionsFromCacheOrStale, setCachedCollections],
  );

  const createCollection = useCallback(
    async (
      name: string,
      metadata: Record<string, any> = {},
      accessToken?: string,
    ): Promise<Collection | undefined> => {
      if (!session?.accessToken && !accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to create collection. Please try again.",
        });
        return;
      }

      const trimmedName = name.trim();
      if (!trimmedName) {
        console.error("Collection name cannot be empty.");
        return undefined;
      }
      const nameExists = collections.some(
        (c) => c.name.toLowerCase() === trimmedName.toLowerCase(),
      );
      if (nameExists) {
        console.warn(`Collection with name "${trimmedName}" already exists.`);
        return undefined;
      }

      const newCollection: CollectionCreate = {
        name: trimmedName,
        metadata,
      };
      const response = await fetch("/api/langconnect/collections", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken || session?.accessToken}`,
        },
        body: JSON.stringify(newCollection),
      });
      if (!response.ok) {
        console.error(`Failed to create collection: ${response.statusText}`);
        return undefined;
      }
      const data = await response.json();
      setCollections((prevCollections) => [...prevCollections, data]);
      // ✅ PHASE 1: Smart Cache Invalidation
      invalidateCollectionSpecific(data.uuid, CollectionCacheEvent.COLLECTION_CREATED);
      return data;
    },
    [collections, session, invalidateCollectionsCache],
  );

  const createCollectionWithSharing = useCallback(
    async (
      name: string,
      metadata: Record<string, any>,
      shareWith?: ShareAtCreation[],
      accessToken?: string,
    ): Promise<Collection | undefined> => {
      if (!session?.accessToken && !accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to create collection. Please try again.",
        });
        return;
      }

      const trimmedName = name.trim();
      if (!trimmedName) {
        console.error("Collection name cannot be empty.");
        return undefined;
      }
      const nameExists = collections.some(
        (c) => c.name.toLowerCase() === trimmedName.toLowerCase(),
      );
      if (nameExists) {
        console.warn(`Collection with name "${trimmedName}" already exists.`);
        return undefined;
      }

      const newCollection: CollectionCreate = {
        name: trimmedName,
        metadata,
        share_with: shareWith,
      };
      
      const response = await fetch("/api/langconnect/collections", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken || session?.accessToken}`,
        },
        body: JSON.stringify(newCollection),
      });
      
      if (!response.ok) {
        console.error(`Failed to create collection: ${response.statusText}`);
        return undefined;
      }
      
      const data = await response.json();
      setCollections((prevCollections) => [...prevCollections, data]);
      // ✅ PHASE 1: Smart Cache Invalidation
      invalidateCollectionSpecific(data.uuid, CollectionCacheEvent.COLLECTION_CREATED);
      
      // Show success message with sharing info
      if (shareWith && shareWith.length > 0) {
        // Check if response indicates notifications were created vs direct grants
        // This is future-proofing for when the backend supports notifications
        const notificationsCreated = data.notifications_created?.length || 0;
        const directGrants = data.shared_with?.length || shareWith.length; // Fallback to requested count
        
        if (notificationsCreated > 0 && directGrants === 0) {
          // Future: all were notifications
          toast.success(
            `Collection created! Sharing request${notificationsCreated > 1 ? 's' : ''} sent to ${notificationsCreated} team member${notificationsCreated > 1 ? 's' : ''}. ` +
            `They'll receive a notification to accept or reject access.`, 
            { richColors: true, duration: 5000 }
          );
        } else if (directGrants > 0 && notificationsCreated === 0) {
          // Current behavior: direct grants  
                  const message = knowledgeMessages.collection.create.successWithSharing(data.name, directGrants);
        notify.success(message.title, {
          description: message.description,
          key: message.key,
        });
        } else if (directGrants > 0 && notificationsCreated > 0) {
          // Future: mixed mode
          toast.success(
            `Collection created! Shared with ${directGrants} team member${directGrants === 1 ? '' : 's'} and sent ` +
            `notification${notificationsCreated > 1 ? 's' : ''} to ${notificationsCreated} team member${notificationsCreated > 1 ? 's' : ''}`, 
            { richColors: true, duration: 5000 }
          );
        } else {
          // Fallback
                  const message = knowledgeMessages.collection.create.successWithSharing(data.name, shareWith.length);
        notify.success(message.title, {
          description: message.description,
          key: message.key,
        });
        }
      } else {
        const message = knowledgeMessages.collection.create.success(data.name);
        notify.success(message.title, {
          description: message.description,
          key: message.key,
        });
      }
      
      return data;
    },
    [collections, session, invalidateCollectionsCache],
  );

  const updateCollection = useCallback(
    async (
      collectionId: string,
      newName: string,
      metadata: Record<string, any>,
    ): Promise<Collection | undefined> => {
      if (!session?.accessToken) {
        toast.error("No session found", {
          richColors: true,
          description: "Failed to update collection. Please try again.",
        });
        return;
      }

      // Find the collection to update
      const collectionToUpdate = collections.find(
        (c) => c.uuid === collectionId,
      );

      if (!collectionToUpdate) {
        toast.error(`Collection with ID "${collectionId}" not found.`, {
          richColors: true,
        });
        return undefined;
      }

      const trimmedNewName = newName.trim();
      if (!trimmedNewName) {
        toast.error("Collection name cannot be empty.", { richColors: true });
        return undefined;
      }

      // Check if the new name already exists (only if name is changing)
      const nameExists = collections.some(
        (c) =>
          c.name.toLowerCase() === trimmedNewName.toLowerCase() &&
          c.name !== collectionToUpdate.name,
      );
      if (nameExists) {
        toast.warning(
          `Collection with name "${trimmedNewName}" already exists.`,
          { richColors: true },
        );
        return undefined;
      }

      const updateData = {
        name: trimmedNewName,
        metadata: metadata,
      };

      const response = await fetch(`/api/langconnect/collections/${collectionId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify(updateData),
      });

      if (!response.ok) {
        toast.error(`Failed to update collection: ${response.statusText}`, {
          richColors: true,
        });
        return undefined;
      }

      const updatedCollection = await response.json();

      // Update the collections state
      setCollections((prevCollections) =>
        prevCollections.map((collection) =>
          collection.uuid === collectionId ? updatedCollection : collection,
        ),
      );
      // ✅ PHASE 1: Smart Cache Invalidation
      invalidateCollectionSpecific(collectionId, CollectionCacheEvent.COLLECTION_UPDATED);

      // Update selected collection if it was the one that got updated
      if (selectedCollection && selectedCollection.uuid === collectionId) {
        setSelectedCollection(updatedCollection);
      }

      return updatedCollection;
    },
    [collections, selectedCollection, session, invalidateCollectionsCache],
  );

  const deleteCollection = useCallback(
    async (collectionId: string): Promise<{ ok: true } | { ok: false; errorMessage: string }> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorMessage: "No session found. Please sign in and try again.",
        };
      }

      const collectionToDelete = collections.find(
        (c) => c.uuid === collectionId,
      );

      if (!collectionToDelete) {
        console.warn(`Collection with ID ${collectionId} not found in local state`);
        return {
          ok: false,
          errorMessage: "Collection not found",
        };
      }

      try {
        const response = await fetch(`/api/langconnect/collections/${collectionId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (!response.ok) {
          let errorDetail = response.statusText;
          try {
            // Try to get more detailed error from response body
            const errorData = await response.json();
            errorDetail = errorData.detail || errorDetail;
          } catch (_) {
            // If we can't parse the JSON, stick with status text
          }
          
          return {
            ok: false,
            errorMessage: errorDetail,
          };
        }

        // HTTP 204 No Content responses have no body, so don't try to parse JSON
        // Just update the state to remove the deleted collection
        setCollections((prevCollections) =>
          prevCollections.filter(
            (collection) => collection.uuid !== collectionId,
          ),
        );
        
        // ✅ PHASE 1: Smart Cache Invalidation
        invalidateCollectionSpecific(collectionId, CollectionCacheEvent.COLLECTION_DELETED);
        
        return { ok: true };
      } catch (error) {
        return {
          ok: false,
          errorMessage: error instanceof Error ? error.message : "Unknown error occurred",
        };
      }
    },
    [collections, session, invalidateCollectionsCache],
  );
  // --- Return combined state and functions ---
  return {
    // Misc
    initialSearchExecuted,
    setInitialSearchExecuted,
    initialFetch,

    // Collections
    collections,
    setCollections,
    collectionsLoading,
    setCollectionsLoading,
    getCollections,
    createCollection,
    createCollectionWithSharing,
    updateCollection,
    deleteCollection,
    refreshCollectionDocumentCount,

    selectedCollection,
    setSelectedCollection,

    // Documents
    documents,
    setDocuments,
    documentsLoading,
    setDocumentsLoading,
    listDocuments,
    deleteDocument,
    
    // Enhanced upload
    handleEnhancedUpload,
    
    // Legacy upload (backward compatibility)
    handleFileUpload,
    handleTextUpload,

    // Job tracking integration
    processingJobs: jobTracking.jobs,
    getJobsByCollection: jobTracking.getJobsByCollection,
    activeJobsCount: jobTracking.getActiveJobs().length,
    cancelJob: jobTracking.cancelJob,
  };
}
