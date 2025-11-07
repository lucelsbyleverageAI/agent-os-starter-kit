#!/bin/bash
# Helper script to export collections from local Docker database
# This bypasses the pooler by connecting directly to the db container

set -e

COLLECTION_NAME="$1"
OUTPUT_FILE="${2:-database/exports/export_$(date +%Y%m%d_%H%M%S).json}"

if [ -z "$COLLECTION_NAME" ]; then
    echo "Usage: $0 <collection_name> [output_file]"
    echo ""
    echo "Example: $0 \"NHS Data Guidance\""
    exit 1
fi

echo "📤 Exporting collection: $COLLECTION_NAME"
echo "   Output: $OUTPUT_FILE"
echo ""

# Run export using Docker exec to bypass pooler
docker exec supabase-db bash -c "
PGPASSWORD=localpass python3 - <<'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/tmp')
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

collection_name = '''$COLLECTION_NAME'''

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='postgres',
    user='postgres',
    password='localpass'
)

# Get collection
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute('''
        SELECT uuid, name, cmetadata, created_at, updated_at
        FROM langconnect.langchain_pg_collection
        WHERE name = %s
    ''', (collection_name,))
    collection = cur.fetchone()

    if not collection:
        print(f'Collection not found: {collection_name}', file=sys.stderr)
        sys.exit(1)

    collection_id = collection['uuid']
    print(f'Found collection: {collection[\"name\"]} ({collection_id})', file=sys.stderr)

    # Get documents
    cur.execute('''
        SELECT id, content, cmetadata, created_at, updated_at
        FROM langconnect.langchain_pg_document
        WHERE collection_id = %s
    ''', (collection_id,))
    documents = cur.fetchall()

    # Get embeddings
    cur.execute('''
        SELECT id, document_id, document as content,
               embedding::text as embedding_vector, cmetadata, created_at, updated_at
        FROM langconnect.langchain_pg_embedding
        WHERE collection_id = %s
    ''', (collection_id,))
    embeddings = cur.fetchall()

    # Get permissions
    cur.execute('''
        SELECT cp.user_id, cp.permission_level, cp.granted_by,
               ur.email, ur.display_name, ur.role
        FROM langconnect.collection_permissions cp
        LEFT JOIN langconnect.user_roles ur ON cp.user_id = ur.user_id
        WHERE cp.collection_id = %s
    ''', (collection_id,))
    permissions = cur.fetchall()

    print(f'Documents: {len(documents)}', file=sys.stderr)
    print(f'Embeddings: {len(embeddings)}', file=sys.stderr)
    print(f'Permissions: {len(permissions)}', file=sys.stderr)

# Convert to dict
def to_dict(row):
    if row is None:
        return None
    return dict(row)

bundle = {
    'export_metadata': {
        'version': '1.0',
        'format': 'collection_export',
        'source_environment': 'local',
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'collection_count': 1
    },
    'user_directory': {},
    'collections': [{
        'collection': to_dict(collection),
        'documents': [to_dict(d) for d in documents],
        'embeddings': [to_dict(e) for e in embeddings],
        'permissions': [to_dict(p) for p in permissions],
        'stats': {
            'document_count': len(documents),
            'embedding_count': len(embeddings),
            'permission_count': len(permissions),
            'embeddings_included': True
        }
    }]
}

# Add users to directory
for perm in permissions:
    user_id = perm['user_id']
    if user_id not in bundle['user_directory']:
        bundle['user_directory'][user_id] = {
            'email': perm.get('email'),
            'display_name': perm.get('display_name'),
            'role': perm.get('role')
        }

print(json.dumps(bundle, indent=2, default=str))

conn.close()
PYTHON_SCRIPT
" > "$OUTPUT_FILE"

if [ -f "$OUTPUT_FILE" ]; then
    SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo ""
    echo "✅ Export complete!"
    echo "   File: $OUTPUT_FILE"
    echo "   Size: $SIZE"
else
    echo "❌ Export failed"
    exit 1
fi
