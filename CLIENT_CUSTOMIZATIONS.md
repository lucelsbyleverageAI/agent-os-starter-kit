# E18 Client Customizations

This document tracks all E18-specific customizations that should NOT be synchronized back to the template repository.

**Client**: E18
**Template**: agent-os-starter-kit
**Last Updated**: 2025-11-06

## Overview

This client repository contains customizations for E18's specific business needs and branding. When merging template updates, these customizations should be preserved using the "ours" merge strategy.

---

## 1. Branding & UI Customizations

### Application Branding
- **App Name**: Changed from "Agent OS" to "e18" branding
- **Logo**: E18-specific logo assets
- **Color Scheme**: E18 brand colors
- **Favicon**: E18 favicon

### Affected Files
- `apps/web/src/app/layout.tsx` - App metadata and title
- `apps/web/public/` - Logo and favicon assets
- Brand-specific styling and theme configurations
- Any component with E18-specific text or branding

### Merge Strategy
When conflicts occur in branding files: **KEEP E18 VERSION (ours)**

---

## 2. NHS Outcomes Data Pipeline

### Description
E18-specific GitHub Actions workflow that connects to production database to refresh NHS outcomes data monthly.

### Affected Files
- `.github/workflows/outcomes-data-pipeline.yml` - Scheduled data refresh workflow
- Any E18-specific data processing scripts or utilities
- NHS-specific configuration files

### Merge Strategy
When conflicts occur: **KEEP E18 VERSION (ours)**
These files are completely client-specific and should never sync to template.

---

## 3. Client-Specific Configuration

### Environment Variables
E18 may have additional environment variables not in the template:
- NHS data connection strings
- E18-specific API keys
- Production URLs and domains

### Affected Files
- `.env.local.example` - May contain E18-specific variable examples
- `docker-compose.production.yml` - May have E18-specific service configs
- Deployment configurations (Coolify, Caddy labels)

### Merge Strategy
**REVIEW CAREFULLY**: Template may add new required variables. Merge both template additions and E18-specific variables.

---

## 4. Production Deployment Configuration

### E18-Specific Settings
- Production URLs (e18-specific domains)
- Coolify deployment labels and routing
- E18-specific SSL/TLS configurations
- E18-specific backup strategies

### Affected Files
- `docker-compose.production.yml`
- Caddy reverse proxy configurations
- Any deployment scripts or infrastructure-as-code

### Merge Strategy
**REVIEW CAREFULLY**: Keep E18 domain/routing config, but accept template infrastructure improvements.

---

## 5. Bug Fixes & Features

### E18-Specific Fixes
The following commits contain E18-specific fixes that may or may not be relevant to template:

- `7f53479` - **fix: Resolve hydration mismatch in agents-combobox**
  **Decision**: Consider contributing back to template (if not E18-specific)

- `1fb6681` - **feat: Rebrand application for e18 client**
  **Decision**: NEVER sync to template (client branding)

### Merge Strategy
Bug fixes should be evaluated case-by-case:
- If generalizable: Cherry-pick to template after E18 deployment succeeds
- If E18-specific: Keep in client repo only

---

## 6. Database Customizations

### E18-Specific Schema
- Custom tables for NHS data
- E18-specific stored procedures or functions
- Client-specific data models

### Affected Files
- `database/migrate.py` - May contain E18-specific migrations
- Custom SQL scripts in `supabase/volumes/`
- E18-specific Supabase edge functions

### Merge Strategy
**REVIEW CAREFULLY**: Merge template schema improvements, preserve E18 additions.

---

## 7. Documentation Changes

### E18-Specific Docs
- This file (CLIENT_CUSTOMIZATIONS.md)
- E18-specific deployment guides
- NHS data pipeline documentation

### Affected Files
- `CLIENT_CUSTOMIZATIONS.md` - Never sync to template
- `TEMPLATE_VERSION.txt` - Never sync to template
- Any E18-specific README sections

### Merge Strategy
**KEEP E18 VERSION**: Documentation is client-specific.

---

## Merge Conflict Resolution Guidelines

### Default Strategy: Template Wins (theirs)
For core platform files, accept template changes:
- LangGraph agent core code
- LangConnect RAG engine
- MCP server core functionality
- Core frontend components
- Package dependencies (review carefully)

### Exception: E18 Customizations Win (ours)
For client-specific files, keep E18 version:
- All branding/UI customizations
- NHS data pipeline
- E18-specific configurations
- Client documentation

### Review Required
Some files need manual review:
- `docker-compose.production.yml` - Merge both
- `.env.local.example` - Merge both
- `package.json` - Accept template, review dependencies
- `apps/web/src/app/layout.tsx` - Keep E18 branding, accept structural improvements

---

## Contributing Back to Template

### Generalizable Improvements
If E18 development produces fixes or features that benefit all clients:

1. Cherry-pick the commit to a new branch
2. Remove any E18-specific references
3. Test against template's clean state
4. Submit PR to template repository
5. Document in TEMPLATE_VERSION.txt

### Example: Hydration Fix
The hydration fix (`7f53479`) may be generalizable if it's not related to E18-specific branding.

**Process:**
1. Verify the fix works in E18 production
2. Check if template codebase has the same issue
3. If yes, create PR to template with the fix
4. Document the contribution

---

## Sync Checklist

When syncing template updates, use this checklist:

- [ ] Review TEMPLATE_VERSION.txt for last sync point
- [ ] Review template CHANGELOG or release notes
- [ ] Identify E18 customizations that might conflict
- [ ] Perform merge with conflict strategy documented here
- [ ] Test thoroughly in development environment
- [ ] Verify E18 branding is intact
- [ ] Verify NHS pipeline still works
- [ ] Check production configuration preserved
- [ ] Update TEMPLATE_VERSION.txt with new version
- [ ] Document any new customizations in this file

---

## Contact

For questions about E18 customizations or merge strategy:
- **Engineer**: Luc (AI Engineer)
- **Client**: E18
- **Template Maintainer**: Leverage.ai
