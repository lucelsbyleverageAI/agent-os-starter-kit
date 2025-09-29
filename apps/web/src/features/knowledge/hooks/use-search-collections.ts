import { useState, useMemo } from "react";
import { debounce } from "lodash";
import type { Collection } from "@/types/collection";
import { getCollectionName } from "./use-knowledge";

export function useSearchCollections(collections: Collection[]) {
  const [collectionSearchTerm, setCollectionSearchTerm] = useState("");

  const debouncedSetSearchTerm = useMemo(
    () => debounce((term: string) => setCollectionSearchTerm(term), 300),
    []
  );

  const filteredCollections = useMemo(() => {
    if (!collectionSearchTerm) {
      return collections;
    }

    const searchLower = collectionSearchTerm.toLowerCase();
    
    return collections.filter((collection) => {
      const name = getCollectionName(collection.name).toLowerCase();
      const description = (collection.metadata?.description || "").toLowerCase();
      
      return (
        name.includes(searchLower) ||
        description.includes(searchLower)
      );
    });
  }, [collections, collectionSearchTerm]);

  return {
    collectionSearchTerm,
    debouncedSetSearchTerm,
    filteredCollections,
  };
} 