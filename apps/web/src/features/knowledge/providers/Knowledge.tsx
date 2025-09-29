import React, { createContext, useContext, PropsWithChildren } from "react";
import { useKnowledge } from "../hooks/use-knowledge";
import { useAuthContext } from "@/providers/Auth";
import { useEffect } from "react";

type KnowledgeContextType = ReturnType<typeof useKnowledge>;

const KnowledgeContext = createContext<KnowledgeContextType | null>(null);

export const KnowledgeProvider: React.FC<PropsWithChildren> = ({ children }) => {
  const knowledgeState = useKnowledge();

  const { session } = useAuthContext();

  useEffect(() => {
    if (
      knowledgeState.collections.length > 0 ||
      knowledgeState.initialSearchExecuted ||
      !session?.accessToken
    ) {
      return;
    }
    knowledgeState.initialFetch(session?.accessToken);
  }, [session?.accessToken]);

  return <KnowledgeContext.Provider value={knowledgeState}>{children}</KnowledgeContext.Provider>;
};

export const useKnowledgeContext = () => {
  const context = useContext(KnowledgeContext);
  if (context === null) {
    throw new Error("useKnowledgeContext must be used within a KnowledgeProvider");
  }
  return context;
};
