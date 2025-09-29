import { Control, FieldPath, FieldValues, Controller } from "react-hook-form";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";
import { useState } from "react";

type SchemaProperty = any; // Simplified type to avoid complex JSONSchema7 types

interface FormFieldRendererProps<T extends FieldValues> {
  control: Control<T>;
  name: FieldPath<T>;
  property: SchemaProperty;
  label: string;
  description?: string;
  required?: boolean;
}

export function FormFieldRenderer<T extends FieldValues>({
  control,
  name,
  property,
  label,
  description,
  required = false,
}: FormFieldRendererProps<T>) {
  const [arrayItems, setArrayItems] = useState<string[]>([]);

  // Helper to get enum options from schema
  const getEnumOptions = (prop: SchemaProperty): string[] => {
    if (prop && typeof prop === 'object' && 'enum' in prop && Array.isArray(prop.enum)) {
      return prop.enum as string[];
    }
    return [];
  };

  // Helper to determine field type from schema
  const getFieldType = (prop: SchemaProperty): string => {
    if (!prop || typeof prop !== 'object') return 'string';
    
    // Handle anyOf patterns (common in LangGraph schemas)
    if ('anyOf' in prop && Array.isArray(prop.anyOf)) {
      const nonNullTypes = prop.anyOf.filter((item: any) => 
        typeof item === 'object' && item.type !== 'null'
      );
      if (nonNullTypes.length > 0 && typeof nonNullTypes[0] === 'object') {
        return nonNullTypes[0].type as string;
      }
    }
    
    return (prop.type as string) || 'string';
  };

  const fieldType = getFieldType(property);
  const enumOptions = getEnumOptions(property);

  return (
    <div className="space-y-2">
      <Label htmlFor={name}>
        {label}
        {required && <span className="text-destructive ml-1">*</span>}
      </Label>
      
      <Controller
        control={control}
        name={name}
        render={({ field }) => {
          // Enum/Select field
          if (enumOptions.length > 0) {
            return (
              <Select
                value={field.value || ""}
                onValueChange={field.onChange}
              >
                <SelectTrigger>
                  <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
                </SelectTrigger>
                <SelectContent>
                  {enumOptions.map((option: string) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            );
          }

          // Array field
          if (fieldType === 'array') {
            return (
              <div className="space-y-2">
                {arrayItems.map((item: string, index: number) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      value={item ?? ""}
                      onChange={(e) => {
                        const newItems = [...arrayItems];
                        newItems[index] = e.target.value;
                        setArrayItems(newItems);
                        field.onChange(newItems);
                      }}
                      placeholder={`${label} item ${index + 1}`}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        const newItems = arrayItems.filter((_, i) => i !== index);
                        setArrayItems(newItems);
                        field.onChange(newItems);
                      }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const newItems = [...arrayItems, ''];
                    setArrayItems(newItems);
                    field.onChange(newItems);
                  }}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add {label} item
                </Button>
              </div>
            );
          }

          // Boolean field
          if (fieldType === 'boolean') {
            return (
              <div className="flex items-center space-x-2">
                <Switch
                  checked={field.value || false}
                  onCheckedChange={field.onChange}
                  id={name}
                />
                <label
                  htmlFor={name}
                  className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                >
                  {field.value ? 'Enabled' : 'Disabled'}
                </label>
              </div>
            );
          }

          // Number field
          if (fieldType === 'number' || fieldType === 'integer') {
            return (
              <Input
                type="number"
                placeholder={`Enter ${label.toLowerCase()}`}
                value={field.value ?? ""}
                onChange={(e) => {
                  const value = fieldType === 'integer' 
                    ? parseInt(e.target.value) || 0
                    : parseFloat(e.target.value) || 0;
                  field.onChange(value);
                }}
              />
            );
          }

          // String field - always use a textarea that starts as one line and can grow
          if (fieldType === 'string') {
            return (
              <Textarea
                placeholder={`Enter ${label.toLowerCase()}`}
                className="resize-y min-h-[2.25rem] max-h-40 block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                rows={1}
                value={field.value ?? ""}
                onChange={field.onChange}
                style={{ overflowWrap: 'break-word', wordBreak: 'break-word' }}
              />
            );
          }

          // Default to text input
          return (
            <Input
              type="text"
              placeholder={`Enter ${label.toLowerCase()}`}
              value={field.value ?? ""}
              onChange={field.onChange}
            />
          );
        }}
      />
      
      {description && (
        <p className="text-sm text-muted-foreground">{description}</p>
      )}
    </div>
  );
} 