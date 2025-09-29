"use client";

import React, { createContext, useContext, PropsWithChildren } from "react";
import { useUsers } from "@/hooks/use-users";
import { useAuthContext } from "@/providers/Auth";
import { useEffect } from "react";

type UsersContextType = ReturnType<typeof useUsers>;

const UsersContext = createContext<UsersContextType | null>(null);

export const UsersProvider: React.FC<PropsWithChildren> = ({ children }) => {
  const usersState = useUsers();
  const { session } = useAuthContext();

  // Auto-fetch users when authenticated
  useEffect(() => {
    if (session?.accessToken && !usersState.loading && usersState.users.length === 0) {
      usersState.fetchUsers();
    }
  }, [session?.accessToken, usersState]);

  return (
    <UsersContext.Provider value={usersState}>
      {children}
    </UsersContext.Provider>
  );
};

export const useUsersContext = () => {
  const context = useContext(UsersContext);
  if (context === null) {
    throw new Error("useUsersContext must be used within a UsersProvider");
  }
  return context;
}; 