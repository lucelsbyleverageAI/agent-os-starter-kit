export type InputSchema = {
  type: "object";
  properties?: Record<string, any>;
  required?: string[];
};

export interface Tool {
  /**
   * The name of the tool
   */
  name: string;
  /**
   * The tool's description
   */
  description?: string;
  /**
   * The tool's input schema
   */
  inputSchema: InputSchema;
  /**
   * The toolkit this tool belongs to
   */
  toolkit?: string;
  /**
   * The display name of the toolkit
   */
  toolkit_display_name?: string;
}

export interface Toolkit {
  /**
   * The toolkit identifier
   */
  name: string;
  /**
   * The display name of the toolkit
   */
  display_name: string;
  /**
   * Tools in this toolkit
   */
  tools: Tool[];
  /**
   * Number of tools in this toolkit
   */
  count: number;
}
