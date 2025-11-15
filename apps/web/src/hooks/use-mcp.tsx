import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { Tool, Toolkit } from "@/types/tool";
import { useState } from "react";

function getMCPUrlOrThrow() {
  if (!process.env.NEXT_PUBLIC_BASE_API_URL) {
    throw new Error("NEXT_PUBLIC_BASE_API_URL is not defined");
  }

  const url = new URL(process.env.NEXT_PUBLIC_BASE_API_URL);
  url.pathname = `${url.pathname}${url.pathname.endsWith("/") ? "" : "/"}oap_mcp`;
  return url;
}

/**
 * Custom hook for interacting with the Model Context Protocol (MCP).
 * Provides functions to connect to an MCP server and list available tools.
 */
export default function useMCP({
  name,
  version,
}: {
  name: string;
  version: string;
}) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [toolkits, setToolkits] = useState<Toolkit[]>([]);
  const [cursor, setCursor] = useState("");



  /**
   * Creates an MCP client and connects it to the specified server URL.
   * @returns A promise that resolves to the connected MCP client instance.
   */
  const createAndConnectMCPClient = async () => {
    const url = getMCPUrlOrThrow();
    const connectionClient = new StreamableHTTPClientTransport(
      new URL(url)
    );
    const mcp = new Client({
      name,
      version,
    });

    await mcp.connect(connectionClient);
    return mcp;
  };

  /**
   * Connects to an MCP server and retrieves the list of available tools.
   * @param nextCursor - Cursor for pagination
   * @returns A promise that resolves to an array of available tools.
   */
  const getTools = async (nextCursor?: string): Promise<Tool[]> => {
    const overallStart = Date.now();
    
    try {
      const connectionStart = Date.now();
      const mcp = await createAndConnectMCPClient();
      const _connectionDuration = Date.now() - connectionStart;
      
      const toolsFetchStart = Date.now();
      const toolsResponse = await mcp.listTools({ cursor: nextCursor });
      const _toolsFetchDuration = Date.now() - toolsFetchStart;
      
      // Transform MCP tools to include toolkit information from meta field
      const transformedTools = toolsResponse.tools.map((tool: any) => {
        
        return {
          ...tool,
          // Extract toolkit info from meta field for backward compatibility
          // Only set if meta fields exist, otherwise let the original fields through
          ...(tool.meta?.toolkit && { toolkit: tool.meta.toolkit }),
          ...(tool.meta?.toolkit_display_name && { toolkit_display_name: tool.meta.toolkit_display_name }),
        };
      });
      
      // Note: Toolkit grouping is handled by the MCP Provider
      
      if (toolsResponse.nextCursor) {
        setCursor(toolsResponse.nextCursor);
      } else {
        setCursor("");
      }
      
      const _overallDuration = Date.now() - overallStart;
      
      return transformedTools;
    } catch (error) {
      const _overallDuration = Date.now() - overallStart;
      throw error;
    }
  };

  /**
   * Calls a tool on the MCP server.
   * @param name - The name of the tool.
   * @param version - The version of the tool. Optional.
   * @param args - The arguments to pass to the tool.
   * @returns A promise that resolves to the response from the tool.
   */
  const callTool = async ({
    name,
    args,
    version,
    timeout = 300000, // 5 minute default timeout for tool execution
  }: {
    name: string;
    args: Record<string, any>;
    version?: string;
    timeout?: number;
  }) => {
    const mcp = await createAndConnectMCPClient();
    const toolParams: {
      name: string;
      arguments: Record<string, any>;
      version?: string;
    } = {
      name,
      arguments: args,
    };

    if (version !== undefined) {
      toolParams.version = version;
    }

    return await mcp.callTool(
      toolParams,
      undefined, // No schema
      {
        timeout,
        resetTimeoutOnProgress: true,
      }
    );
  };



  return {
    getTools,
    callTool,
    createAndConnectMCPClient,
    tools,
    setTools,
    toolkits,
    setToolkits,
    cursor,
  };
}
