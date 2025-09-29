import { NextRequest, NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import { join } from 'path';

// Define allowed template names for security
const ALLOWED_TEMPLATES = [
  'invite',
  'confirmation', 
  'recovery',
  'magic-link',
  'email-change'
];

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ template: string }> }
) {
  try {
    const { template: templateName } = await params;
    
    // Validate template name
    if (!ALLOWED_TEMPLATES.includes(templateName)) {
      return new NextResponse('Template not found', { status: 404 });
    }
    
    // Read the template file from public directory
    const templatePath = join(process.cwd(), 'public', 'templates', `${templateName}.html`);
    const templateContent = await readFile(templatePath, 'utf-8');
    
    // Return the template with proper content type
    return new NextResponse(templateContent, {
      status: 200,
      headers: {
        'Content-Type': 'text/html',
        'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
      },
    });
  } catch (error) {
    console.error('Error serving email template:', error);
    return new NextResponse('Template not found', { status: 404 });
  }
} 