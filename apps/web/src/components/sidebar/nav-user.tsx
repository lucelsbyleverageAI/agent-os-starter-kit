"use client";

import { useEffect, useState } from "react";
import {
  ChevronsUpDown,
  LogOut,
  User,
  Loader2,
  TriangleAlert,
  MessageSquarePlus,
} from "lucide-react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuthContext } from "@/providers/Auth";
import { useRouter } from "next/navigation";
import { notify } from "@/utils/toast";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { AppFeedbackDialog } from "@/components/feedback/AppFeedbackDialog";

export function NavUser() {
  const { isMobile } = useSidebar();
  const { user: authUser, signOut, isAuthenticated, isLoading: authLoading } = useAuthContext();
  const router = useRouter();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [hasMounted, setHasMounted] = useState(false);
  const [feedbackDialogOpen, setFeedbackDialogOpen] = useState(false);
  const { resetStore } = useConfigStore();

  useEffect(() => {
    setHasMounted(true);
  }, []);

  // Use auth user if available, otherwise use default user
  const displayUser = authUser
    ? {
        name: authUser.displayName || authUser.email?.split("@")[0] || "User",
        email: authUser.email || "",
        avatar: authUser.avatarUrl || "",
        company: "",
        firstName: authUser.firstName || "",
        lastName: authUser.lastName || "",
      }
    : {
        name: "Guest",
        email: "Not signed in",
        avatar: "",
        company: "",
        firstName: "",
        lastName: "",
      };

  const handleSignOut = async () => {
    try {
      setIsSigningOut(true);
      const { error } = await signOut();

      if (error) {
        console.error("Error signing out:", error);
        toast.error("Error signing out", { richColors: true });
        return;
      }

      router.push("/signin");
    } catch (err) {
      console.error("Error during sign out:", err);
      toast.error("Error signing out", { richColors: true });
    } finally {
      setIsSigningOut(false);
    }
  };

  const handleSignIn = () => {
    router.push("/signin");
  };

  const handleClearLocalData = () => {
    resetStore();
    notify.success("Local data cleared", {
      description: "Please refresh the page to complete the reset.",
      key: "nav:clear-data:success",
    });
  };

  const isProdEnv = process.env.NODE_ENV === "production";

  const initials = hasMounted
    ? (displayUser.name || "").substring(0, 2).toUpperCase()
    : "GU"; // Stable SSR placeholder to avoid hydration mismatch

  // Only show text details once mounted and not loading to avoid SSR/CSR mismatch with auth
  const showUserText = hasMounted && !authLoading && isAuthenticated && !!authUser;

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground h-16 group-data-[collapsible=icon]:p-0!">
              <Avatar className="h-8 w-8 rounded-lg">
                <AvatarImage
                  src={displayUser.avatar}
                  alt={displayUser.name}
                />
                <AvatarFallback className="rounded-lg">
                  <span suppressHydrationWarning>{initials}</span>
                </AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate font-semibold" suppressHydrationWarning>
                  {showUserText ? displayUser.name : ""}
                </span>
                <span className="truncate text-xs" suppressHydrationWarning>
                  {showUserText ? displayUser.email : ""}
                </span>
                {"company" in displayUser && (
                  <span
                    className="text-muted-foreground truncate text-xs"
                    suppressHydrationWarning
                  >
                    {showUserText ? (displayUser as any).company : ""}
                  </span>
                )}
              </div>
              <ChevronsUpDown className="ml-auto size-4 group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <Avatar className="h-8 w-8 rounded-lg">
                  <AvatarImage
                    src={displayUser.avatar}
                    alt={displayUser.name}
                  />
                  <AvatarFallback className="rounded-lg">
                    <span suppressHydrationWarning>{initials}</span>
                  </AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold" suppressHydrationWarning>
                    {showUserText ? displayUser.name : ""}
                  </span>
                  <span className="truncate text-xs" suppressHydrationWarning>
                    {showUserText ? displayUser.email : ""}
                  </span>
                  {"company" in displayUser && (
                    <span
                      className="text-muted-foreground truncate text-xs"
                      suppressHydrationWarning
                    >
                      {showUserText ? (displayUser as any).company : ""}
                    </span>
                  )}
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />

            <DropdownMenuLabel className="text-xs text-muted-foreground px-2 py-1.5">
              Theme
            </DropdownMenuLabel>
            <ThemeToggle />

            <DropdownMenuSeparator />

            {isAuthenticated && (
              <DropdownMenuItem onClick={() => setFeedbackDialogOpen(true)}>
                <MessageSquarePlus className="mr-2 h-4 w-4" />
                Submit Feedback
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />

            {isAuthenticated ? (
              <DropdownMenuItem
                onClick={handleSignOut}
                disabled={isSigningOut}
              >
                {isSigningOut ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing out...
                  </>
                ) : (
                  <>
                    <LogOut className="mr-2 h-4 w-4" />
                    Sign out
                  </>
                )}
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={handleSignIn}>
                <User className="mr-2 h-4 w-4" />
                Sign in
              </DropdownMenuItem>
            )}
            {!isProdEnv && (
              <DropdownMenuItem onClick={handleClearLocalData}>
                <TriangleAlert className="mr-2 h-4 w-4 text-red-500" />
                Clear local data
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>

      <AppFeedbackDialog
        open={feedbackDialogOpen}
        onOpenChange={setFeedbackDialogOpen}
      />
    </SidebarMenu>
  );
}
