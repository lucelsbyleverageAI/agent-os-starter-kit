#!/usr/bin/env node
/**
 * Sanitise n8n exported JSON files to remove personal/project-specific metadata.
 *
 * - Targets:
 *   - Workflows: ./n8n/data/workflows/*.json
 *   - Credentials: ./n8n/data/credentials/*.json
 * - Removals:
 *   - Top-level `shared` array (contains project + user info)
 *   - Any nested `project` object(s) within `shared`
 *   - Top-level `projectId` if present
 *   - Any top-level `owner`, `createdBy`, `updatedBy` if present
 * - Preserves workflow functionality: does NOT change `active`, nodes, or connections
 */

const fs = require('fs');
const path = require('path');

const root = process.cwd();
const workflowsDir = path.join(root, 'n8n', 'data', 'workflows');
const credentialsDir = path.join(root, 'n8n', 'data', 'credentials');

function isJsonFile(filePath) {
  return filePath.toLowerCase().endsWith('.json');
}

function listJsonFiles(dirPath) {
  if (!fs.existsSync(dirPath)) return [];
  return fs
    .readdirSync(dirPath)
    .filter((f) => isJsonFile(f))
    .map((f) => path.join(dirPath, f));
}

function sanitiseWorkflow(obj) {
  // Remove personal/project metadata if present
  delete obj.shared;
  delete obj.projectId;
  delete obj.owner;
  delete obj.createdBy;
  delete obj.updatedBy;
  // Do NOT touch `active`, `nodes`, `connections`, etc.
  return obj;
}

function sanitiseCredential(obj) {
  // Remove personal/project metadata if present
  delete obj.shared;
  delete obj.projectId;
  delete obj.owner;
  delete obj.createdBy;
  delete obj.updatedBy;
  // Keep encrypted data and id/name as-is (not personal)
  return obj;
}

function processFiles(files, transform) {
  let changed = 0;
  for (const file of files) {
    try {
      const raw = fs.readFileSync(file, 'utf8');
      // Handle compact or pretty JSON
      const data = JSON.parse(raw);
      const before = JSON.stringify(data);
      const afterObj = transform(data);
      const after = JSON.stringify(afterObj);
      if (after !== before) {
        // Write back in the original compact style to minimise diffs
        fs.writeFileSync(file, after, 'utf8');
        changed += 1;
      }
    } catch (err) {
      console.error(`Failed to sanitise ${file}:`, err.message);
    }
  }
  return changed;
}

const workflowFiles = listJsonFiles(workflowsDir);
const credentialFiles = listJsonFiles(credentialsDir);

const changedWorkflows = processFiles(workflowFiles, sanitiseWorkflow);
const changedCredentials = processFiles(credentialFiles, sanitiseCredential);

console.log(
  `Sanitised n8n exports: ${changedWorkflows} workflows, ${changedCredentials} credentials.`
);

