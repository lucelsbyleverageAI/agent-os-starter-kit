"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuthContext } from "@/providers/Auth";
import { z } from "zod";

// Form validation schemas
const basePasswordSchema = z.object({
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/[0-9]/, "Password must contain at least one number"),
  confirmPassword: z.string(),
});

const resetPasswordSchema = basePasswordSchema.refine(
  (data) => data.password === data.confirmPassword,
  {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  }
);

const invitePasswordSchema = basePasswordSchema
  .extend({
    firstName: z.string().min(1, "First name is required"),
    lastName: z.string().min(1, "Last name is required"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type ResetFormValues = {
  password: string;
  confirmPassword: string;
  firstName?: string;
  lastName?: string;
};

export default function ResetPasswordInterface() {
  const { updatePassword, updateUser } = useAuthContext();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [formValues, setFormValues] = useState<ResetFormValues>({
    password: "",
    confirmPassword: "",
    firstName: "",
    lastName: "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof ResetFormValues, string>>>({});
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isInvitation, setIsInvitation] = useState<boolean>(false);

  // Check if this is an invitation flow
  useEffect(() => {
    const type = searchParams.get("type");
    const inviteToken = searchParams.get("token");
    
    // If there's a type=invite or an invite token, this is an invitation
    if (type === "invite" || inviteToken) {
      setIsInvitation(true);
    }
  }, [searchParams]);

  const validateForm = () => {
    try {
      const schema = isInvitation ? invitePasswordSchema : resetPasswordSchema;
      schema.parse(formValues);
      setErrors({});
      return true;
    } catch (error) {
      if (error instanceof z.ZodError) {
        const formattedErrors: Partial<Record<keyof ResetFormValues, string>> = {};
        error.errors.forEach((err) => {
          if (err.path[0]) {
            formattedErrors[err.path[0] as keyof ResetFormValues] = err.message;
          }
        });
        setErrors(formattedErrors);
      }
      return false;
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormValues((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);

    if (!validateForm()) return;

    setIsLoading(true);

    try {
      // First, check if we have a token_hash that needs to be verified
      const tokenHash = searchParams.get("token_hash");
      const type = searchParams.get("type");

      if (tokenHash && type) {
        // Verify the token first to establish a session
        const { getSupabaseClient } = await import("@/lib/auth/supabase-client");
        const supabase = getSupabaseClient();
        
        const { error: verifyError } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type: type as any,
        });

        if (verifyError) {
          let errorMessage = verifyError.message;
          
          if (errorMessage.includes("Token has expired")) {
            errorMessage = "This link has expired. Please request a new password reset email.";
          } else if (errorMessage.includes("Invalid token")) {
            errorMessage = "This link is invalid or has already been used. Please request a new one.";
          }
          
          setAuthError(errorMessage);
          return;
        }
      }

      // Now update the password with the established session
      const { error } = await updatePassword(formValues.password);

      if (!error && isInvitation && formValues.firstName && formValues.lastName) {
        // Update user profile information for invitations
        await updateUser({
          firstName: formValues.firstName,
          lastName: formValues.lastName,
        });
      }

      if (error) {
        // Provide more helpful error messages
        let errorMessage = error.message;
        
        if (errorMessage.includes("New password should be different")) {
          errorMessage = "Please choose a different password from your current one.";
        } else if (errorMessage.includes("Password should be")) {
          errorMessage = "Password must be at least 8 characters long.";
        } else if (errorMessage.includes("Unable to validate email address")) {
          errorMessage = "The password reset link has expired or is invalid. Please request a new one.";
        } else if (errorMessage.includes("Token has expired")) {
          errorMessage = "This link has expired. Please request a new password reset email.";
        } else if (errorMessage.includes("Auth session missing")) {
          errorMessage = "Session expired. Please click the link in your email again.";
        }
        
        setAuthError(errorMessage);
        return;
      }

      // Redirect to the sign-in page with appropriate success message
      const successMessage = isInvitation 
        ? "Welcome! Your account has been set up successfully. Please sign in with your new password."
        : "Your password has been successfully reset. Please sign in with your new password.";
        
      router.push(`/signin?message=${encodeURIComponent(successMessage)}`);
    } catch (err) {
      console.error("Password reset error:", err);
      setAuthError("An unexpected error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center py-10">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-center text-2xl">
            {isInvitation ? "Set Up Your Password" : "Reset Password"}
          </CardTitle>
          <CardDescription className="text-center">
            {isInvitation 
              ? "Welcome! Please set up your account by providing your details and creating a password."
              : "Please enter your new password"
            }
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit}
            className="space-y-4"
          >
            {isInvitation && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="firstName">First Name</Label>
                    <Input
                      id="firstName"
                      name="firstName"
                      type="text"
                      placeholder="John"
                      value={formValues.firstName || ""}
                      onChange={handleInputChange}
                      aria-invalid={!!errors.firstName}
                    />
                    {errors.firstName && (
                      <p className="text-destructive text-sm">{errors.firstName}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="lastName">Last Name</Label>
                    <Input
                      id="lastName"
                      name="lastName"
                      type="text"
                      placeholder="Doe"
                      value={formValues.lastName || ""}
                      onChange={handleInputChange}
                      aria-invalid={!!errors.lastName}
                    />
                    {errors.lastName && (
                      <p className="text-destructive text-sm">{errors.lastName}</p>
                    )}
                  </div>
                </div>
              </>
            )}

            <div className="space-y-2">
              <Label htmlFor="password">New Password</Label>
              <PasswordInput
                id="password"
                name="password"
                placeholder="Create a new password"
                value={formValues.password}
                onChange={handleInputChange}
                aria-invalid={!!errors.password}
              />
              {errors.password && (
                <p className="text-destructive text-sm">{errors.password}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <PasswordInput
                id="confirmPassword"
                name="confirmPassword"
                placeholder="Confirm your new password"
                value={formValues.confirmPassword}
                onChange={handleInputChange}
                aria-invalid={!!errors.confirmPassword}
              />
              {errors.confirmPassword && (
                <p className="text-destructive text-sm">
                  {errors.confirmPassword}
                </p>
              )}
            </div>

            {authError && (
              <Alert variant="destructive">
                <AlertDescription>{authError}</AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading}
            >
              {isLoading 
                ? (isInvitation ? "Setting up..." : "Resetting...") 
                : (isInvitation ? "Set Up Account" : "Reset Password")
              }
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
