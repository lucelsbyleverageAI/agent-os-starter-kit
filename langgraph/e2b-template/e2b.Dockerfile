# E2B Custom Template for Skills DeepAgent
# Pre-installs document processing and data science libraries
#
# Build with: e2b template build -c "/root/.jupyter/start-up.sh"
#
FROM e2bdev/code-interpreter:latest

# ============================================
# Document Processing Libraries
# ============================================

# PDF Processing
RUN pip install --no-cache-dir \
    pypdf \
    pdfplumber \
    PyMuPDF

# Microsoft Office Formats
RUN pip install --no-cache-dir \
    python-docx \
    python-pptx \
    openpyxl \
    xlrd

# ============================================
# Data Processing & Analysis
# ============================================

RUN pip install --no-cache-dir \
    pandas \
    numpy \
    beautifulsoup4 \
    lxml \
    markdownify \
    Pillow \
    chardet

# ============================================
# Additional Utilities
# ============================================

RUN pip install --no-cache-dir \
    requests \
    httpx \
    pyyaml \
    python-dateutil \
    tabulate

# ============================================
# Node.js Packages (for skills)
# ============================================

# Switch to root for global npm install
USER root

# docx - Create Word documents programmatically (used by docx skill)
RUN npm install -g docx

# Switch back to default user
USER user
