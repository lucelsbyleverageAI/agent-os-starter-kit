"use client";

import { useEffect } from "react";
import { initializeFileTypeIcons } from "@fluentui/react-file-type-icons";

let initialized = false;

export function FluentIconsInit() {
  useEffect(() => {
    if (!initialized) {
      initializeFileTypeIcons();
      initialized = true;
    }
  }, []);

  return null;
}
