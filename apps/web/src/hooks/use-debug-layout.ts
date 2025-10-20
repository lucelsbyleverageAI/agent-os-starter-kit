import { useEffect } from 'react';

export function useDebugLayout(componentName: string) {
  useEffect(() => {
    console.log(`🔍 [${componentName}] Mounting debug layout observer...`);

    const checkAllElements = () => {
      // Find the configuration sidebar with multiple selectors
      let sidebar = document.querySelector('[data-slot="configuration-sidebar"]');

      if (!sidebar) {
        // Try alternative selectors
        const possibleSelectors = [
          '.fixed.top-0.right-0.z-10.h-screen',
          '.fixed.right-0.border-l',
          '[class*="fixed"][class*="right-0"][class*="h-screen"]',
          'div.fixed[class*="w-"][class*="md:w-"]',
        ];

        for (const selector of possibleSelectors) {
          sidebar = document.querySelector(selector);
          if (sidebar) {
            console.log(`📌 [${componentName}] Found sidebar with selector: ${selector}`);
            break;
          }
        }
      }

      if (!sidebar) {
        // Last resort - find by checking all fixed positioned elements
        const allFixed = document.querySelectorAll('.fixed');
        console.log(`🔍 [${componentName}] Checking ${allFixed.length} fixed elements...`);

        allFixed.forEach((el) => {
          const rect = el.getBoundingClientRect();
          const classes = el.className;
          if (classes.includes('right-0') && rect.width > 100 && rect.width < 800) {
            console.log(`📍 [${componentName}] Potential sidebar:`, {
              width: rect.width,
              classes: classes.substring(0, 100)
            });
            sidebar = el;
          }
        });
      }

      if (!sidebar) {
        console.log(`❌ [${componentName}] Sidebar not found after trying all selectors`);
        return;
      }

      const sidebarRect = sidebar.getBoundingClientRect();
      console.log(`📏 [${componentName}] Sidebar width: ${sidebarRect.width}px, classes: ${sidebar.className.substring(0, 100)}`);

      // Skip measurement if sidebar is clearly closed or in transition
      if (sidebarRect.width < 100) {
        console.log(`⏸️ [${componentName}] Skipping measurement - sidebar appears closed (width: ${sidebarRect.width}px)`);
        return;
      }

      // Check all elements within the sidebar
      const allElements = sidebar.querySelectorAll('*');
      const overflowingElements: Array<{element: Element, width: number, sidebarWidth: number}> = [];

      allElements.forEach((element) => {
        const rect = element.getBoundingClientRect();

        // Check if element is wider than sidebar
        if (rect.width > sidebarRect.width) {
          overflowingElements.push({
            element,
            width: rect.width,
            sidebarWidth: sidebarRect.width
          });
        }

        // Also check computed styles
        const styles = window.getComputedStyle(element);

        // Check for problematic CSS properties
        if (styles.width === 'max-content' || styles.width === 'fit-content') {
          console.warn(`⚠️ [${componentName}] Element has problematic width:`, {
            element,
            width: styles.width,
            class: element.className,
            tagName: element.tagName
          });
        }

        // Check for elements without width constraints
        if (styles.minWidth === '0px' && styles.maxWidth === 'none' && styles.width === 'auto') {
          const hasOverflowHidden = styles.overflow === 'hidden' || styles.overflowX === 'hidden';
          if (!hasOverflowHidden && rect.width > 400) {
            console.warn(`📐 [${componentName}] Unconstrained element:`, {
              element,
              width: rect.width,
              class: element.className,
              tagName: element.tagName
            });
          }
        }
      });

      if (overflowingElements.length > 0) {
        console.error(`🚨🚨🚨 [${componentName}] FOUND ${overflowingElements.length} OVERFLOWING ELEMENTS:`, overflowingElements);
        overflowingElements.forEach(({element, width, sidebarWidth}) => {
          console.error(`  • Overflow:`, {
            element,
            elementWidth: width,
            sidebarWidth: sidebarWidth,
            overflow: width - sidebarWidth,
            class: element.className,
            tag: element.tagName,
            text: element.textContent?.substring(0, 50)
          });

          // Temporarily add a red border to overflowing elements
          (element as HTMLElement).style.border = '2px solid red';
        });
      } else {
        console.log(`✅ [${componentName}] No overflowing elements found`);
      }

      // Check specific problem areas
      const selects = sidebar.querySelectorAll('select, [role="combobox"]');
      selects.forEach((select) => {
        const rect = select.getBoundingClientRect();
        console.log(`🎯 [${componentName}] Select element:`, {
          width: rect.width,
          class: select.className,
          computedWidth: window.getComputedStyle(select).width
        });
      });

      const buttons = sidebar.querySelectorAll('button');
      buttons.forEach((button) => {
        const rect = button.getBoundingClientRect();
        if (rect.width > 400) {
          console.warn(`🔘 [${componentName}] Wide button found:`, {
            width: rect.width,
            text: button.textContent,
            class: button.className
          });
        }
      });

      const textareas = sidebar.querySelectorAll('textarea');
      textareas.forEach((textarea) => {
        const rect = textarea.getBoundingClientRect();
        const styles = window.getComputedStyle(textarea);
        console.log(`📝 [${componentName}] Textarea:`, {
          width: rect.width,
          computedWidth: styles.width,
          fieldSizing: (styles as any).fieldSizing || 'not set',
          class: textarea.className
        });
      });
    };

    // Run checks at different times to catch async content
    // Wait a bit for any transitions to complete
    setTimeout(checkAllElements, 100);
    setTimeout(checkAllElements, 600);
    setTimeout(checkAllElements, 1500);
    setTimeout(checkAllElements, 3000);

    // Also run on any DOM mutations
    const observer = new MutationObserver(() => {
      console.log(`🔄 [${componentName}] DOM mutation detected, checking...`);
      checkAllElements();
    });

    // Start observing
    setTimeout(() => {
      let sidebar = document.querySelector('[data-slot="configuration-sidebar"]') ||
                    document.querySelector('.fixed.top-0.right-0.z-10.h-screen') ||
                    document.querySelector('.fixed.right-0.border-l');

      if (!sidebar) {
        const allFixed = document.querySelectorAll('.fixed');
        allFixed.forEach((el) => {
          const rect = el.getBoundingClientRect();
          const classes = el.className;
          if (classes.includes('right-0') && rect.width > 100 && rect.width < 800) {
            sidebar = el;
          }
        });
      }

      if (sidebar) {
        console.log(`👁️ [${componentName}] Starting MutationObserver on sidebar`);
        observer.observe(sidebar, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['style', 'class']
        });
      } else {
        console.log(`❌ [${componentName}] Could not start MutationObserver - sidebar not found`);
      }
    }, 100);

    return () => {
      observer.disconnect();
    };
  }, [componentName]);
}