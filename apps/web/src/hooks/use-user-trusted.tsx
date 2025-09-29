"use client";

import { useState, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';

const USER_ID_COOKIE_NAME = 'user_id';

/**
 * Simple user identification hook for trusted frontend mode.
 * This mimics the working application's approach:
 * 1. Check for existing user_id cookie
 * 2. If not found, generate new UUID and store in cookie
 * 3. Provides persistent user identity across sessions
 */
export function useUserTrusted() {
  const [userId, setUserId] = useState<string>(() => {
    // Only run on client-side
    if (typeof window === 'undefined') {
      return '';
    }

    // Check for existing cookie first
    const userIdCookie = getCookie(USER_ID_COOKIE_NAME);
    if (userIdCookie) {
      return userIdCookie;
    }
    
    // Generate new UUID if no cookie exists
    const newUserId = uuidv4();
    setCookie(USER_ID_COOKIE_NAME, newUserId);
    return newUserId;
  });

  // Ensure userId is set on client-side hydration
  useEffect(() => {
    if (!userId && typeof window !== 'undefined') {
      const userIdCookie = getCookie(USER_ID_COOKIE_NAME);
      if (userIdCookie) {
        setUserId(userIdCookie);
      } else {
        const newUserId = uuidv4();
        setCookie(USER_ID_COOKIE_NAME, newUserId);
        setUserId(newUserId);
      }
    }
  }, [userId]);

  return { userId };
}

// Helper functions for cookie management
function getCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop()?.split(';').shift();
  }
  return undefined;
}

function setCookie(name: string, value: string, days: number = 365) {
  if (typeof document === 'undefined') return;
  
  const expires = new Date();
  expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/`;
} 