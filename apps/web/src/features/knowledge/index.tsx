"use client";

import type React from "react";
import { useState } from "react";
import { ChevronRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Search } from "@/components/ui/tool-search";
import { useKnowledgeContext } from "./providers/Knowledge";
import EmptyCollectionsState from "./components/empty-collections";
import { CollectionCard, CollectionCardLoading } from "./components/collection-card";
import type { Collection } from "@/types/collection";
import { getCollectionName } from "./hooks/use-knowledge";

export default function KnowledgeInterface() {
  const {
    collections,
    initialSearchExecuted,
  } = useKnowledgeContext();

  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 12; // Show more items in grid layout

  // Simple search filtering
  const filteredCollections = collections.filter((collection) => {
    if (!searchTerm) return true;
    const searchLower = searchTerm.toLowerCase();
    const name = getCollectionName(collection.name).toLowerCase();
    const description = (collection.metadata?.description || "").toLowerCase();
    return name.includes(searchLower) || description.includes(searchLower);
  });

  // Calculate pagination
  const totalPages = Math.ceil(filteredCollections.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedCollections = filteredCollections.slice(startIndex, endIndex);

  const handleLoadMore = () => {
    setCurrentPage(prev => prev + 1);
  };

  const hasMore = currentPage < totalPages;

  if (initialSearchExecuted && !collections.length) {
    return <EmptyCollectionsState />;
  }

  return (
    <div className="flex w-full flex-col gap-6">
      {/* Search Section */}
      <div className="flex w-full items-center justify-start">
        <Search
          onSearchChange={(value) => setSearchTerm(value)}
          placeholder="Search collections..."
          className="w-full md:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.667rem)]"
        />
      </div>

      {/* Collections Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {!initialSearchExecuted &&
          Array.from({ length: 6 }).map((_, index) => (
            <CollectionCardLoading key={`collection-card-loading-${index}`} />
          ))}
        
        {paginatedCollections.map((collection: Collection) => (
          <CollectionCard
            key={collection.uuid}
            collection={collection}
          />
        ))}
        
        {filteredCollections.length === 0 && searchTerm && initialSearchExecuted && (
          <p className="col-span-full my-4 w-full text-center text-sm text-slate-500">
            No collections found matching "{searchTerm}".
          </p>
        )}
        
        {collections.length === 0 && !searchTerm && initialSearchExecuted && (
          <p className="col-span-full my-4 w-full text-center text-sm text-slate-500">
            No collections available.
          </p>
        )}
      </div>

      {/* Load More Button */}
      {!searchTerm && hasMore && initialSearchExecuted && (
        <div className="mt-4 flex justify-center">
          <Button
            onClick={handleLoadMore}
            variant="outline"
            className="gap-1 px-2.5"
          >
            Load More Collections
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
