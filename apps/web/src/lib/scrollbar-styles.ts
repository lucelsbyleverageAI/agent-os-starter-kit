/**
 * Common scrollbar styles used throughout the application
 * Provides consistent custom webkit scrollbar styling
 */

export const scrollbarStyles = [
  "[&::-webkit-scrollbar]:w-1.5",
  "[&::-webkit-scrollbar-thumb]:rounded-full", 
  "[&::-webkit-scrollbar-thumb]:bg-gray-300",
  "[&::-webkit-scrollbar-track]:bg-transparent"
];

/**
 * Scrollbar utilities for different scroll directions
 */
export const scrollbarClasses = {
  // Vertical scrolling with custom scrollbar
  y: `overflow-y-auto ${scrollbarStyles.join(" ")}`,
  
  // Horizontal scrolling with custom scrollbar  
  x: `overflow-x-auto ${scrollbarStyles.join(" ")}`,
  
  // Both directions with custom scrollbar
  both: `overflow-auto ${scrollbarStyles.join(" ")}`,
  
  // Scroll with hidden scrollbar (for cases where you want scrolling but no visible scrollbar)
  hidden: "overflow-auto scrollbar-hide",
} as const;

/**
 * Get scrollbar classes as an array (useful with cn() utility)
 */
export const getScrollbarClasses = (direction: keyof typeof scrollbarClasses = 'both') => {
  return scrollbarClasses[direction].split(" ");
}; 