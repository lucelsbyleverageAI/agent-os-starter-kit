#!/usr/bin/env python3
"""Test production database connection and get user UUIDs."""

import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Try to load from .env.local
env_file = Path(__file__).parent.parent.parent / '.env.local'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:  # Don't override existing env vars
                    os.environ[key] = value

password = os.getenv('POSTGRES_PASSWORD_PRODUCTION')
if not password:
    print('❌ POSTGRES_PASSWORD_PRODUCTION not found in .env.local or environment')
    print('Add this line to .env.local: POSTGRES_PASSWORD_PRODUCTION=your-password')
    sys.exit(1)

print('🔌 Connecting to production database via SSH tunnel (localhost:5433)...')
print('   Make sure SSH tunnel is open: ./database/collection_transfer/tunnel_to_production.sh')
print()
try:
    conn = psycopg2.connect(
        host='localhost',
        port=5433,
        database='postgres',
        user='postgres',
        password=password,
        connect_timeout=5
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''
            SELECT user_id, email, role
            FROM langconnect.user_roles
            ORDER BY email
        ''')
        users = cur.fetchall()

        if users:
            print(f'✅ Found {len(users)} production users:')
            print()
            for user in users:
                print(f'   {user["email"]:40s} → {user["user_id"]}')
        else:
            print('⚠️  No users found in production')

    conn.close()
    print('\n✅ Connection successful!')

except Exception as e:
    print(f'❌ Connection failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
