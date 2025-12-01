import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
  ConfigurableFieldSandboxConfigMetadata,
  ConfigurableFieldSkillsMetadata,
  ConfigurableFieldUIMetadata,
} from "@/types/configurable";
import { Assistant, GraphSchema } from "@langchain/langgraph-sdk";
import { toast } from "sonner";

function getUiConfig(
  value: unknown,
): { type: string; [key: string]: any } | undefined {
  if (
    typeof value !== "object" ||
    !value ||
    (!("metadata" in value) && !("x_oap_ui_config" in value))
  ) {
    return undefined;
  }
  const uiConfig: Record<string, any> =
    "metadata" in value
      ? (value.metadata as Record<string, any>).x_oap_ui_config
      : (value as Record<string, any>).x_oap_ui_config;
  if (!uiConfig) {
    return undefined;
  }

  if (
    typeof uiConfig === "object" &&
    "type" in uiConfig &&
    uiConfig.type &&
    typeof uiConfig.type === "string"
  ) {
    return {
      ...uiConfig,
      type: uiConfig.type,
    };
  }

  return undefined;
}

/**
 * Converts a LangGraph configuration schema into an array of UI metadata
 * for configurable fields.
 *
 * This function iterates through the properties of the provided schema,
 * looking for a specific metadata field (`x_oap_ui_config`). If found,
 * it extracts the UI configuration and constructs a ConfigurableFieldUIMetadata
 * object, using the property key as the label.
 *
 * @param schema - The LangGraph configuration schema to process.
 * @returns An array of ConfigurableFieldUIMetadata objects representing
 *          the UI configuration for fields found in the schema, or an empty
 *          array if the schema is invalid or contains no UI configurations.
 */
export function configSchemaToConfigurableFields(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldUIMetadata[] {
  if (!schema || !schema.properties) {
    return [];
  }

  const fields: ConfigurableFieldUIMetadata[] = [];
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    if (uiConfig && ["mcp", "rag", "skills", "sandbox_config", "hidden", "agent_name", "agent_description", "agents_builder", "agents"].includes(uiConfig.type)) {
      continue;
    }

    if (uiConfig) {
      const config = uiConfig as Omit<ConfigurableFieldUIMetadata, "label">;
      fields.push({
        label: key,
        ...config,
      });
      continue;
    }

    // If the `x_oap_ui_config` metadata is not found/is missing the `type` field, default to text input
    fields.push({
      label: key,
      type: "text",
    });
  }
  return fields;
}

export function configSchemaToConfigurableTools(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldMCPMetadata[] {
  if (!schema || !schema.properties) {
    return [];
  }

  const fields: ConfigurableFieldMCPMetadata[] = [];
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    if (!uiConfig || uiConfig.type !== "mcp") {
      continue;
    }

    if (!process.env.NEXT_PUBLIC_MCP_SERVER_URL) {
      toast.error("Can not configure MCP tool without MCP server URL", {
        richColors: true,
      });
      continue;
    }

    fields.push({
      label: key,
      type: uiConfig.type,
      default: {
        url: process.env.NEXT_PUBLIC_MCP_SERVER_URL,
        tools: [],
        ...(uiConfig.default ?? {}),
      },
    });
  }
  return fields;
}

export function configSchemaToRagConfig(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldRAGMetadata | undefined {
  if (!schema || !schema.properties) {
    return undefined;
  }

  let ragField: ConfigurableFieldRAGMetadata | undefined;
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    
    if (!uiConfig || uiConfig.type !== "rag") {
      continue;
    }

    // Extract nested enabled_tools metadata if it exists
    let toolGroupsMetadata: any = undefined;
    let refPath: string | undefined = undefined;
    
    // Check for $ref in multiple possible locations
    if (typeof value === "object" && value) {
      // Case 1: Direct $ref
      if ("$ref" in value) {
        refPath = (value as any).$ref;
      }
      // Case 2: $ref inside anyOf array (Pydantic Optional pattern)
      else if ("anyOf" in value && Array.isArray((value as any).anyOf)) {
        // Find the first item with a $ref (ignore null types)
        const refItem = (value as any).anyOf.find((item: any) => 
          typeof item === "object" && item && "$ref" in item
        );
        
        if (refItem) {
          refPath = refItem.$ref;
        }
      }
    }
    
    // If we found a $ref, look it up in $defs
    if (refPath) {
      // Extract the definition name from $ref (e.g., "#/$defs/RagConfig" -> "RagConfig")
      const defName = refPath.split('/').pop();
      
      // Look in $defs for the actual RagConfig schema
      if (schema.$defs && defName && schema.$defs[defName]) {
        const ragConfigDef = schema.$defs[defName];
        
        if (typeof ragConfigDef === "object" && "properties" in ragConfigDef) {
          const ragProperties = (ragConfigDef as any).properties;
          
          if (ragProperties && "enabled_tools" in ragProperties) {
            const enabledToolsConfig = getUiConfig(ragProperties.enabled_tools);
            
            if (enabledToolsConfig) {
              toolGroupsMetadata = enabledToolsConfig;
            }
          }
        }
      }
    }
    // Fallback: check if properties are directly on the value
    else if (typeof value === "object" && value && "properties" in value) {
      const ragProperties = (value as any).properties;
      if (ragProperties && "enabled_tools" in ragProperties) {
        const enabledToolsConfig = getUiConfig(ragProperties.enabled_tools);
        if (enabledToolsConfig) {
          toolGroupsMetadata = enabledToolsConfig;
        }
      }
    }

    ragField = {
      label: key,
      type: uiConfig.type,
      default: uiConfig.default,
      toolGroupsMetadata, // Add the nested metadata
    };
    break;
  }
  
  return ragField;
}

export function configSchemaToSkillsConfig(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldSkillsMetadata | undefined {
  if (!schema || !schema.properties) {
    return undefined;
  }

  let skillsField: ConfigurableFieldSkillsMetadata | undefined;
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    if (!uiConfig || uiConfig.type !== "skills") {
      continue;
    }

    skillsField = {
      label: key,
      type: "skills",
      default: {
        skills: uiConfig.default?.skills ?? [],
      },
      disabled_when: uiConfig.disabled_when,
    };
    break;
  }
  return skillsField;
}

export function configSchemaToSandboxConfig(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldSandboxConfigMetadata | undefined {
  if (!schema || !schema.properties) {
    return undefined;
  }

  let sandboxField: ConfigurableFieldSandboxConfigMetadata | undefined;
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    if (!uiConfig || uiConfig.type !== "sandbox_config") {
      continue;
    }

    sandboxField = {
      label: key,
      type: "sandbox_config",
      default: {
        timeout_seconds: uiConfig.default?.timeout_seconds ?? 600,
        pip_packages: uiConfig.default?.pip_packages ?? [],
      },
      disabled_when: uiConfig.disabled_when,
    };
    break;
  }
  return sandboxField;
}

export function configSchemaToAgentsConfig(
  schema: GraphSchema["config_schema"],
): ConfigurableFieldAgentsMetadata | undefined {
  if (!schema || !schema.properties) {
    return undefined;
  }

  let agentsField: ConfigurableFieldAgentsMetadata | undefined;
  for (const [key, value] of Object.entries(schema.properties)) {
    const uiConfig = getUiConfig(value);
    if (!uiConfig || uiConfig.type !== "agents") {
      continue;
    }

    // Extract sub-agent item schema from array definition
    let itemSchema: ConfigurableFieldUIMetadata[] | undefined;
    let refPath: string | undefined = undefined;

    // Check for $ref in multiple possible locations (for array item types)
    if (typeof value === "object" && value) {
      // Case 1: Array with items.$ref
      if ("items" in value && typeof (value as any).items === "object") {
        const items = (value as any).items;
        if ("$ref" in items) {
          refPath = items.$ref;
        } else if ("anyOf" in items && Array.isArray(items.anyOf)) {
          const refItem = items.anyOf.find((item: any) => 
            typeof item === "object" && item && "$ref" in item
          );
          if (refItem) {
            refPath = refItem.$ref;
          }
        }
      }
      // Case 2: anyOf with array type
      else if ("anyOf" in value && Array.isArray((value as any).anyOf)) {
        for (const anyOfItem of (value as any).anyOf) {
          if (anyOfItem && "items" in anyOfItem && typeof anyOfItem.items === "object") {
            if ("$ref" in anyOfItem.items) {
              refPath = anyOfItem.items.$ref;
              break;
            }
          }
        }
      }
    }

    // If we found a $ref, look it up in $defs and extract its properties
    if (refPath && schema.$defs) {
      const defName = refPath.split('/').pop();
      if (defName && schema.$defs[defName]) {
        const itemDef = schema.$defs[defName];
        if (typeof itemDef === "object" && "properties" in itemDef) {
          // Extract UI config for each property in the sub-agent schema
          itemSchema = [];
          for (const [propKey, propValue] of Object.entries((itemDef as any).properties)) {
            const propUiConfig = getUiConfig(propValue);
            if (propUiConfig) {
              itemSchema.push({
                label: propKey,
                ...propUiConfig,
                type: propUiConfig.type as ConfigurableFieldUIMetadata['type'],
              });
            } else {
              // Default to text input if no UI config
              itemSchema.push({
                label: propKey,
                type: "text",
              });
            }
          }
        }
      }
    }

    agentsField = {
      label: key,
      type: uiConfig.type,
      mode: uiConfig.mode, // optional builder/selector hint
      default: uiConfig.default,
      itemSchema, // Include the extracted item schema
    };
    break;
  }
  return agentsField;
}

type ExtractedConfigs = {
  configFields: ConfigurableFieldUIMetadata[];
  toolConfig: ConfigurableFieldMCPMetadata[];
  ragConfig: ConfigurableFieldRAGMetadata[];
  agentsConfig: ConfigurableFieldAgentsMetadata[];
  skillsConfig: ConfigurableFieldSkillsMetadata[];
  sandboxConfig: ConfigurableFieldSandboxConfigMetadata[];
};

export function extractConfigurationsFromAgent({
  agent,
  schema,
}: {
  agent: Assistant;
  schema: GraphSchema["config_schema"];
}): ExtractedConfigs {
  const configFields = configSchemaToConfigurableFields(schema);
  const toolConfig = configSchemaToConfigurableTools(schema);
  const ragConfig = configSchemaToRagConfig(schema);
  const agentsConfig = configSchemaToAgentsConfig(schema);
  const skillsConfig = configSchemaToSkillsConfig(schema);
  const sandboxConfig = configSchemaToSandboxConfig(schema);

  const configFieldsWithDefaults = configFields.map((f) => {
    const defaultConfig = (agent.config as Record<string, any>)?.[f.label] ?? f.default;
    return {
      ...f,
      default: defaultConfig,
    };
  });

  const configurable = (agent.config as Record<string, any>) ?? ({} as Record<string, any>);

  const configToolsWithDefaults = toolConfig.map((f) => {
    const defaultConfig = (configurable[f.label] ??
      f.default) as ConfigurableFieldMCPMetadata["default"];
    return {
      ...f,
      default: defaultConfig,
    };
  });

  const configRagWithDefaults = ragConfig
    ? {
        ...ragConfig,
        default: {
          collections:
            (
              configurable[
                ragConfig.label
              ] as ConfigurableFieldRAGMetadata["default"]
            )?.collections ??
            ragConfig.default?.collections ??
            [],
          langconnect_api_url:
            configurable[ragConfig.label]?.langconnect_api_url ??
            process.env.NEXT_PUBLIC_LANGCONNECT_API_URL,
          enabled_tools:
            configurable[ragConfig.label]?.enabled_tools ??
            ragConfig.default?.enabled_tools ??
            ["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_read_image", "collection_grep_files"],
        },
      }
    : undefined;

  const configurableAgentsWithDefaults = agentsConfig
    ? {
        ...agentsConfig,
        default:
          Array.isArray(configurable[agentsConfig.label]) &&
          (configurable[agentsConfig.label] as any[]).length > 0
            ? (configurable[agentsConfig.label] as {
                agent_id?: string;
                deployment_url?: string;
                name?: string;
              }[])
            : Array.isArray(agentsConfig.default)
              ? agentsConfig.default
              : [],
      }
    : undefined;

  const configurableSkillsWithDefaults = skillsConfig
    ? {
        ...skillsConfig,
        default: {
          skills:
            configurable[skillsConfig.label]?.skills ??
            skillsConfig.default?.skills ??
            [],
        },
      }
    : undefined;

  const configurableSandboxWithDefaults = sandboxConfig
    ? {
        ...sandboxConfig,
        default: {
          timeout_seconds:
            configurable[sandboxConfig.label]?.timeout_seconds ??
            sandboxConfig.default?.timeout_seconds ??
            600,
          pip_packages:
            configurable[sandboxConfig.label]?.pip_packages ??
            sandboxConfig.default?.pip_packages ??
            [],
        },
      }
    : undefined;

  return {
    configFields: configFieldsWithDefaults,
    toolConfig: configToolsWithDefaults,
    ragConfig: configRagWithDefaults ? [configRagWithDefaults] : [],
    agentsConfig: configurableAgentsWithDefaults
      ? [configurableAgentsWithDefaults]
      : [],
    skillsConfig: configurableSkillsWithDefaults
      ? [configurableSkillsWithDefaults]
      : [],
    sandboxConfig: configurableSandboxWithDefaults
      ? [configurableSandboxWithDefaults]
      : [],
  };
}

export function getConfigurableDefaults(
  configFields: ConfigurableFieldUIMetadata[],
  toolConfig: ConfigurableFieldMCPMetadata[],
  ragConfig: ConfigurableFieldRAGMetadata[],
  agentsConfig: ConfigurableFieldAgentsMetadata[],
  skillsConfig?: ConfigurableFieldSkillsMetadata[],
  sandboxConfig?: ConfigurableFieldSandboxConfigMetadata[],
): Record<string, any> {
  const defaults: Record<string, any> = {};
  configFields.forEach((field) => {
    defaults[field.label] = field.default;
  });
  toolConfig.forEach((field) => {
    defaults[field.label] = field.default;
  });
  ragConfig.forEach((field) => {
    defaults[field.label] = field.default;
  });
  agentsConfig.forEach((field) => {
    defaults[field.label] = field.default;
  });
  skillsConfig?.forEach((field) => {
    defaults[field.label] = field.default;
  });
  sandboxConfig?.forEach((field) => {
    defaults[field.label] = field.default;
  });
  return defaults;
}
