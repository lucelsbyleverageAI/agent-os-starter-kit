import { NextRequest, NextResponse } from 'next/server';

export interface OpenRouterKeyInfo {
  label: string;
  limit: number | null;
  limit_remaining: number | null;
  usage: number;
  usage_daily: number;
  usage_weekly: number;
  usage_monthly: number;
  is_free_tier: boolean;
}

export interface OpenRouterUsageResponse {
  data: OpenRouterKeyInfo;
}

/**
 * GET /api/openrouter/usage
 *
 * Proxies the OpenRouter /api/v1/key endpoint to fetch current credit balance
 * and usage statistics. Uses server-side OPENROUTER_API_KEY to authenticate.
 */
export async function GET(request: NextRequest) {
  try {
    const apiKey = process.env.OPENROUTER_API_KEY;

    if (!apiKey) {
      return NextResponse.json(
        { error: 'OpenRouter API key not configured' },
        { status: 500 }
      );
    }

    const response = await fetch('https://openrouter.ai/api/v1/key', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('OpenRouter API error:', response.status, errorText);
      return NextResponse.json(
        { error: `OpenRouter API error: ${response.status}` },
        { status: response.status }
      );
    }

    const data: OpenRouterUsageResponse = await response.json();

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching OpenRouter usage:', error);
    return NextResponse.json(
      { error: 'Failed to fetch usage data' },
      { status: 500 }
    );
  }
}
