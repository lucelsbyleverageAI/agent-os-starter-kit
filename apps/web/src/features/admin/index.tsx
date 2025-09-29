"use client";

import { AdminDashboard } from "@/components/admin/admin-dashboard";
import { RoleGuard, useUserRole } from "@/providers/UserRole";
import { AccessDeniedRedirect } from "./access-denied-redirect";

const LoadingFallback = () => {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
        <p className="text-muted-foreground">Verifying permissions...</p>
      </div>
    </div>
  );
};

const AdminFallback = () => {
  const { loading, roleValidated } = useUserRole();
  
  // If still loading or role hasn't been validated yet, show loading
  if (loading || !roleValidated) {
    return <LoadingFallback />;
  }
  
  // Role has been validated and user is not dev_admin, redirect
  return <AccessDeniedRedirect />;
};

export const AdminFeature = () => {
  return (
    <RoleGuard roles={['dev_admin']} fallback={<AdminFallback />}>
      <AdminDashboard />
    </RoleGuard>
  );
};

// Also exporting the component as default
export default AdminFeature; 