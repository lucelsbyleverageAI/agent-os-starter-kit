"use client";

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useCallback,
} from "react";
import { useAuthContext } from "./Auth";

export type UserRole = 'dev_admin' | 'business_admin' | 'user';

interface UserRoleContextType {
  /**
   * The user's role in the system
   */
  userRole: UserRole;
  /**
   * Whether the user is a dev admin (can manage graphs and system-wide permissions)
   */
  isDevAdmin: boolean;
  /**
   * Whether the user is a business admin (can manage users and business permissions)
   */
  isBusinessAdmin: boolean;
  /**
   * Whether the user can manage other users
   */
  canManageUsers: boolean;
  /**
   * Whether the role data is currently loading
   */
  loading: boolean;
  /**
   * Whether the role was determined with a valid session (not a fallback)
   */
  roleValidated: boolean;
  /**
   * Error message if role fetch failed
   */
  error: string | null;
  /**
   * Refresh the user role from the API
   */
  refreshUserRole: () => Promise<void>;
}

const UserRoleContext = createContext<UserRoleContextType | undefined>(undefined);

export const UserRoleProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { session, isLoading: authLoading } = useAuthContext();
  const [userRole, setUserRole] = useState<UserRole>('user');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleValidated, setRoleValidated] = useState(false);

  const fetchUserRole = useCallback(async () => {
    if (authLoading || !session?.accessToken || !session?.user?.id) {
      setUserRole('user');
      setError(null);
      setRoleValidated(false); // Role is fallback, not validated
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const headers = {
        Authorization: `Bearer ${session.accessToken}`,
        'Content-Type': 'application/json',
      };

      // Get the user's actual role from their user record
      const userId = session.user.id;
            
      const userResponse = await fetch(`/api/langconnect/users/${userId}`, {
        headers,
      });

      if (userResponse.status === 404) {
        // User not found in LangConnect database, default to user role
        setUserRole('user');
        setRoleValidated(false); // Role is fallback, not validated
        return;
      }

      if (userResponse.status === 401) {
        // Unauthorized access for user, session may be invalid - default to user role
        setUserRole('user');
        setRoleValidated(false); // Role is fallback, not validated
        return;
      }

      const userData = await userResponse.json();
            
      const role = userData.role as UserRole;
      
      setUserRole(role);
      setRoleValidated(true); // Role was successfully validated with session
      
    } catch (_err) {
      // Network error or other issue - default to user role
      setUserRole('user');
      setRoleValidated(false); // Role is fallback due to error
    } finally {
      setLoading(false);
    }
  }, [authLoading, session?.accessToken, session?.user?.id]);

  // Load user role when session changes
  useEffect(() => {
    fetchUserRole();
  }, [authLoading, session?.accessToken, fetchUserRole]);

  // Derived permission properties
  const isDevAdmin = userRole === 'dev_admin';
  const isBusinessAdmin = userRole === 'business_admin';
  const canManageUsers = isDevAdmin || isBusinessAdmin;

  const userRoleContextValue: UserRoleContextType = {
    userRole,
    isDevAdmin,
    isBusinessAdmin,
    canManageUsers,
    loading,
    error,
    refreshUserRole: fetchUserRole,
    roleValidated,
  };

  return (
    <UserRoleContext.Provider value={userRoleContextValue}>
      {children}
    </UserRoleContext.Provider>
  );
};

/**
 * Hook to access user role context
 */
export const useUserRole = (): UserRoleContextType => {
  const context = useContext(UserRoleContext);
  if (context === undefined) {
    throw new Error("useUserRole must be used within a UserRoleProvider");
  }
  return context;
};

/**
 * HOC to conditionally render components based on user role
 */
export const withUserRole = <P extends object>(
  Component: React.ComponentType<P>,
  requiredRoles: UserRole[]
) => {
  return (props: P) => {
    const { userRole, loading } = useUserRole();
    
    if (loading) {
      return null; // Or a loading spinner
    }
    
    if (!requiredRoles.includes(userRole)) {
      return null; // User doesn't have required role
    }
    
    return <Component {...props} />;
  };
};

/**
 * Component to conditionally render children based on user role
 */
export const RoleGuard: React.FC<{
  children: ReactNode;
  roles: UserRole[];
  fallback?: ReactNode;
}> = ({ children, roles, fallback = null }) => {
  const { userRole, loading } = useUserRole();
  
  if (loading) {
    return <>{fallback}</>;
  }
  
  if (!roles.includes(userRole)) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
};

export default UserRoleContext; 