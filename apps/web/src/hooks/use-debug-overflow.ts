import { useEffect, useRef } from 'react';

export function useDebugOverflow(componentName: string) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const checkOverflow = () => {
      const element = ref.current;
      if (!element) return;

      const rect = element.getBoundingClientRect();
      const parent = element.parentElement;
      const parentRect = parent?.getBoundingClientRect();

      // Check if element is wider than its parent
      if (parentRect && rect.width > parentRect.width) {
        console.warn(`🚨 OVERFLOW DETECTED in ${componentName}:`, {
          component: componentName,
          elementWidth: rect.width,
          parentWidth: parentRect.width,
          overflow: rect.width - parentRect.width,
          element: element,
          classList: element.className,
        });
      }

      // Check all child elements
      const children = element.querySelectorAll('*');
      children.forEach((child) => {
        const childRect = child.getBoundingClientRect();
        if (childRect.width > rect.width) {
          console.warn(`🚨 CHILD OVERFLOW in ${componentName}:`, {
            parent: componentName,
            childElement: child,
            childWidth: childRect.width,
            parentWidth: rect.width,
            overflow: childRect.width - rect.width,
            childClass: child.className,
            childTag: child.tagName,
          });
        }
      });
    };

    // Check immediately
    checkOverflow();

    // Check after a delay (for async content)
    const timeoutId = setTimeout(checkOverflow, 1000);

    // Check on resize
    const resizeObserver = new ResizeObserver(checkOverflow);
    resizeObserver.observe(ref.current);

    return () => {
      clearTimeout(timeoutId);
      resizeObserver.disconnect();
    };
  }, [componentName]);

  return ref;
}