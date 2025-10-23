import { useEffect } from 'react';

export function useGlobalOverflowCheck(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    const checkForOverflow = () => {
      console.log('🌍 Starting global overflow check...');

      // Get viewport width
      const viewportWidth = window.innerWidth;
      console.log(`📐 Viewport width: ${viewportWidth}px`);

      // Check all elements
      const allElements = document.querySelectorAll('*');
      const overflowing: any[] = [];

      allElements.forEach((element) => {
        const rect = element.getBoundingClientRect();

        // Check if element extends beyond viewport
        if (rect.right > viewportWidth || rect.width > viewportWidth) {
          const styles = window.getComputedStyle(element);

          // Skip hidden or very small elements
          if (styles.display === 'none' ||
              styles.visibility === 'hidden' ||
              rect.height < 1) {
            return;
          }

          overflowing.push({
            element,
            right: rect.right,
            width: rect.width,
            left: rect.left,
            overflow: Math.max(rect.right - viewportWidth, 0),
            classes: element.className,
            tag: element.tagName,
            text: (element.textContent || '').substring(0, 50)
          });
        }
      });

      if (overflowing.length > 0) {
        console.error('🚨🚨🚨 GLOBAL OVERFLOW DETECTED!', overflowing.length, 'elements');

        // Sort by overflow amount
        overflowing.sort((a, b) => b.overflow - a.overflow);

        // Show top 10 worst offenders
        overflowing.slice(0, 10).forEach((item, index) => {
          console.error(`${index + 1}. Overflow by ${item.overflow}px:`, {
            ...item,
            element: item.element
          });

          // Add red outline to first 3
          if (index < 3 && item.element instanceof HTMLElement) {
            item.element.style.outline = '3px solid red';
            item.element.style.outlineOffset = '-3px';
          }
        });

        // Also check if the configuration sidebar is among them
        const sidebarOverflow = overflowing.find(item =>
          item.classes?.includes('fixed') &&
          item.classes?.includes('right-0')
        );

        if (sidebarOverflow) {
          console.error('🎯 CONFIGURATION SIDEBAR IS OVERFLOWING:', sidebarOverflow);
        }
      } else {
        console.log('✅ No global overflow detected');
      }

      // Also specifically check for elements that might be in the sidebar
      const fixedElements = document.querySelectorAll('.fixed');
      fixedElements.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && el.className.includes('right-0')) {
          console.log('📊 Fixed right element found:', {
            width: rect.width,
            expectedMaxWidth: el.className.includes('md:w-') ? 576 : 320, // md:w-[36rem] = 576px, w-80 = 320px
            classes: el.className.substring(0, 150)
          });

          // Check children for overflow
          const children = el.querySelectorAll('*');
          children.forEach((child) => {
            const childRect = child.getBoundingClientRect();
            if (childRect.width > rect.width + 10) { // Allow 10px tolerance
              console.error('🔴 Child overflowing sidebar:', {
                parentWidth: rect.width,
                childWidth: childRect.width,
                overflow: childRect.width - rect.width,
                child: child,
                childClasses: child.className
              });
            }
          });
        }
      });
    };

    // Run checks
    setTimeout(checkForOverflow, 100);
    setTimeout(checkForOverflow, 1000);
    setTimeout(checkForOverflow, 2500);

    // Also run on window resize
    const handleResize = () => {
      console.log('📏 Window resized, checking for overflow...');
      checkForOverflow();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [enabled]);
}