# E2B Custom Template for Skills DeepAgent

This directory contains the E2B sandbox template configuration for the Skills DeepAgent.

## Pre-installed Libraries

### Document Processing
| Library | Version | Use Case |
|---------|---------|----------|
| `pypdf` | latest | Read/write PDF text and metadata |
| `pdfplumber` | latest | Extract tables and layout-aware text from PDFs |
| `PyMuPDF` | latest | Advanced PDF processing (fitz) |
| `python-docx` | latest | Read/write Microsoft Word (.docx) |
| `python-pptx` | latest | Read/write PowerPoint (.pptx) |
| `openpyxl` | latest | Read/write Excel (.xlsx) |
| `xlrd` | latest | Read older Excel (.xls) files |

### Data Processing
| Library | Version | Use Case |
|---------|---------|----------|
| `pandas` | latest | DataFrames, CSV/Excel I/O |
| `numpy` | latest | Numerical computing |
| `beautifulsoup4` | latest | HTML/XML parsing |
| `lxml` | latest | Fast XML/HTML processing |
| `markdownify` | latest | Convert HTML to Markdown |
| `Pillow` | latest | Image processing |
| `chardet` | latest | Character encoding detection |

### Utilities
| Library | Version | Use Case |
|---------|---------|----------|
| `requests` | latest | HTTP client |
| `httpx` | latest | Async HTTP client |
| `pyyaml` | latest | YAML parsing |
| `python-dateutil` | latest | Date parsing |
| `tabulate` | latest | Pretty-print tables |

## Building the Template

### Prerequisites

1. Install the E2B CLI:
   ```bash
   npm install -g @e2b/cli
   ```

2. Login to E2B:
   ```bash
   e2b auth login
   ```

### Build Steps

1. Navigate to this directory:
   ```bash
   cd langgraph/e2b-template
   ```

2. Initialize the template (first time only):
   ```bash
   e2b template init
   ```

3. Build the template:
   ```bash
   e2b template build -c "/root/.jupyter/start-up.sh"
   ```

4. Note the template ID from the output (e.g., `my-template-abc123`)

5. Add to your `.env.local`:
   ```
   E2B_TEMPLATE_ID=my-template-abc123
   ```

## Updating the Template

After modifying `e2b.Dockerfile`:

```bash
e2b template build -c "/root/.jupyter/start-up.sh"
```

The template ID remains the same; a new version is published.

## Template Management

List your templates:
```bash
e2b template list
```

Delete a template:
```bash
e2b template delete <template-id>
```
