# PDF Preview Implementation - Troubleshooting Log

## Goal
Add PDF preview functionality to the file preview panel (`file-preview-panel.tsx`) that displays PDF files in a scrollable view with page numbers, similar to the existing Word document preview using `docx-preview`.

## Current State
The file preview panel successfully previews:
- DOCX (using `docx-preview` library)
- XLSX/XLS (using `xlsx` library)
- CSV (custom parser)
- Markdown (using `react-markdown`)
- Code files (using `react-syntax-highlighter`)
- Images (native `<img>` tag)

PDF files currently show "Preview Not Available" fallback.

## Attempted Solutions

### Attempt 1: react-pdf with dynamic import
**Approach**: Use `react-pdf` library (wraps Mozilla's PDF.js) with dynamic import to reduce bundle size.

**Code**:
```typescript
const { Document, Page, pdfjs } = await import("react-pdf");
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
```

**Result**: ❌ Failed
```
TypeError: Object.defineProperty called on non-object
at Object.defineProperty (<anonymous>)
at __webpack_require__.r (webpack.js)
```

**Reason**: Incompatibility between `react-pdf`/`pdfjs-dist` and Next.js 15's webpack configuration. The ES module system conflicts with how webpack processes the library.

---

### Attempt 2: next/dynamic with ssr: false
**Approach**: Create separate `pdf-viewer.tsx` component and load it using `next/dynamic` with `ssr: false` to ensure client-only rendering.

**Code**:
```typescript
const PdfViewer = dynamic(
  () => import("./pdf-viewer").then((mod) => mod.PdfViewer),
  { ssr: false, loading: () => <Loader2 /> }
);
```

**Result**: ❌ Failed
Same webpack error occurred even with SSR disabled. The error happens during client-side webpack bundling, not SSR.

---

### Attempt 3: react-pdf CSS imports
**Approach**: Import react-pdf's CSS for text and annotation layers.

**Code**:
```typescript
import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";
```

**Result**: ❌ Failed
```
Module not found: Can't resolve 'react-pdf/dist/esm/Page/AnnotationLayer.css'
```

**Reason**: CSS paths have changed in react-pdf v10 and/or Next.js can't resolve them.

---

### Attempt 4: Native browser PDF viewer with object/embed
**Approach**: Create blob URL from ArrayBuffer and use native `<object>` and `<embed>` tags.

**Code**:
```typescript
const blob = new Blob([data], { type: "application/pdf" });
const url = URL.createObjectURL(blob);
return (
  <object data={url} type="application/pdf">
    <embed src={url} type="application/pdf" />
  </object>
);
```

**Result**: ❌ Failed - Blank screen
The blob URL was created successfully but the object/embed rendered as blank/empty.

---

### Attempt 5: Native browser PDF viewer with iframe
**Approach**: Use iframe with blob URL instead of object/embed.

**Code**:
```typescript
<iframe
  src={`${objectUrl}#toolbar=1&navpanes=1&scrollbar=1`}
  className="w-full h-full"
/>
```

**Result**: ❌ Failed - Black/dark screen
The iframe rendered but showed a black screen instead of the PDF content. Console showed:
```
[Violation] Potential permissions policy violation: fullscreen is not allowed in this document.
```

---

### Attempt 6: PDF.js from CDN (ES Module version)
**Approach**: Load PDF.js v4.x from CDN as ES module, render pages to canvas, convert to images.

**Code**:
```typescript
const script = document.createElement("script");
script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs";
script.type = "module";
```

**Result**: ❌ Failed
ES module dynamic import from CDN doesn't work in Next.js context.

---

### Attempt 7: PDF.js from CDN (Legacy non-module version)
**Approach**: Load PDF.js v3.x legacy build which attaches to `window.pdfjsLib`.

**Code**:
```typescript
const script = document.createElement("script");
script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
// Legacy build attaches to window.pdfjsLib
```

**Result**: ⚠️ Partial Success then Failed
```
TypeError: Cannot perform Construct on a detached ArrayBuffer
```

**Reason**: PDF.js transfers ownership of the ArrayBuffer, and React re-renders cause it to be used when already detached.

---

### Attempt 8: ArrayBuffer copy before PDF.js
**Approach**: Copy the ArrayBuffer before passing to PDF.js to prevent detachment issues.

**Code**:
```typescript
const dataCopy = data.slice(0);
const loadingTask = pdfjsLib.getDocument({ data: dataCopy });
```

**Result**: ⚠️ Renders but infinite loop
The PDF renders successfully ("Rendered page 1/1" in console) but:
1. `onLoadSuccess` callback triggers parent state update
2. Parent re-renders PdfViewer
3. Effect runs again
4. Infinite loop occurs
5. UI shows "Loading PDF..." forever

Console shows repeated:
```
[PDF Viewer] Copied ArrayBuffer, size: 1387
[PDF Viewer] Loading PDF document...
[PDF Viewer] Rendered page 1/1
[PDF Viewer] PDF loaded, pages: 1
```

---

## Root Causes Identified

1. **react-pdf/pdfjs-dist + Next.js 15 webpack incompatibility**: The ES module structure of pdfjs-dist doesn't work with Next.js 15's webpack configuration, causing `Object.defineProperty called on non-object` errors.

2. **ArrayBuffer transfer semantics**: PDF.js uses `Transferable` objects which detach the original ArrayBuffer after use. React re-renders then fail because the ArrayBuffer is empty.

3. **React effect loop**: The `onLoadSuccess` callback pattern causes an infinite render loop because calling it updates parent state, which re-renders the child, which runs the effect again.

---

## Potential Solutions to Try

1. **Fix the infinite loop** in current implementation by:
   - Using a ref to track if already loaded
   - Memoizing the onLoadSuccess callback
   - Moving page state to parent component

2. **Use @pdfslick/react** - A newer PDF.js wrapper that may have better Next.js compatibility

3. **Use pdf-lib** for parsing + canvas for rendering - Different approach that doesn't use pdfjs-dist

4. **Configure Next.js webpack** to properly handle pdfjs-dist:
   ```javascript
   // next.config.js
   webpack: (config) => {
     config.resolve.alias.canvas = false;
     // other pdfjs-dist specific configs
   }
   ```

5. **Use an iframe with a PDF viewer service** - Google Docs viewer, PDF.js viewer hosted separately, etc.

---

## Files Modified
- `apps/web/src/features/chat/components/file-preview-panel.tsx` - Main preview component
- `apps/web/src/features/chat/components/pdf-viewer.tsx` - New PDF viewer component (created)
- `apps/web/package.json` - Added react-pdf dependency

## Dependencies Added
- `react-pdf@10.2.0` (installed but not working due to webpack issues)
- `pdfjs-dist@5.4.296` (transitive dependency)
