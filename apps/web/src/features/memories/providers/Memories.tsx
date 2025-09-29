import React, { createContext, useContext, PropsWithChildren, useEffect } from "react";
import { useMemories } from "../hooks/use-memories";
import { useAuthContext } from "@/providers/Auth";

type MemoriesContextType = ReturnType<typeof useMemories>;

const MemoriesContext = createContext<MemoriesContextType | null>(null);

export const MemoriesProvider: React.FC<PropsWithChildren> = ({ children }) => {
  const memoriesState = useMemories();
  const { session } = useAuthContext();

  useEffect(() => {
    if (
      memoriesState.memories.length > 0 ||
      memoriesState.initialSearchExecuted ||
      !session?.accessToken
    ) {
      return;
    }
    
    // Initial fetch when the component mounts and user is authenticated
    memoriesState.fetchMemories();
  }, [session?.accessToken, memoriesState.fetchMemories, memoriesState.memories.length, memoriesState.initialSearchExecuted]);

  return (
    <MemoriesContext.Provider value={memoriesState}>
      {children}
    </MemoriesContext.Provider>
  );
};

export const useMemoriesContext = (): MemoriesContextType => {
  const context = useContext(MemoriesContext);
  if (!context) {
    throw new Error("useMemoriesContext must be used within a MemoriesProvider");
  }
  return context;
};
