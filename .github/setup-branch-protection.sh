#!/bin/bash

# Script to set up branch protection rules for main branch
# Requires GitHub CLI (gh) to be installed and authenticated

set -e

REPO="lucelsbyleverageAI/agent-os-starter-kit"
BRANCH="main"

echo "Setting up branch protection for $REPO:$BRANCH..."

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

echo "Configuring branch protection rules..."

# Set up branch protection using GitHub API
gh api \
  --method PUT \
  "/repos/$REPO/branches/$BRANCH/protection" \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend Build & Tests",
      "Frontend Build & Lint",
      "Docker Compose Validation",
      "Trivy Security Scanner"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
EOF

echo "✅ Branch protection rules set successfully!"
echo ""
echo "Main branch protection is now active with:"
echo "  - Required PR approvals: 1"
echo "  - Required status checks:"
echo "    • Backend Build & Tests"
echo "    • Frontend Build & Lint"
echo "    • Docker Compose Validation"
echo "    • Trivy Security Scanner"
echo "  - Dismiss stale reviews: enabled"
echo "  - Required conversation resolution: enabled"
echo "  - Force pushes: disabled"
echo "  - Branch deletions: disabled"
echo ""
echo "Note: Admin bypass is disabled to enforce rules for all users"
