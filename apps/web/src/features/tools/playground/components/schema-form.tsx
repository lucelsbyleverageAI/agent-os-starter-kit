"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import _ from "lodash";

interface SchemaFormProps {
  schema: any;
  onChange: (values: any) => void;
  values: any;
}

interface ArrayItem {
  id: string;
  value: any;
}

export function SchemaForm({ schema, onChange, values }: SchemaFormProps) {
  const [formValues, setFormValues] = useState<Record<string, any>>(
    values || {},
  );

  useEffect(() => {
    // Initialize default values from schema
    if (schema && schema.properties) {
      const defaults: any = {};
      Object.entries(schema.properties).forEach(
        ([key, prop]: [string, any]) => {
          if (prop.default !== undefined && formValues[key] === undefined) {
            defaults[key] = prop.default;
          }
        },
      );

      if (Object.keys(defaults).length > 0) {
        setFormValues((prev) => ({ ...prev, ...defaults }));
      }
    }
  }, [schema, formValues]);

  useEffect(() => {
    onChange(formValues);
  }, [formValues, onChange]);

  const handleChange = (name: string, value: any) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  if (!schema || !schema.properties) {
    return <div className="text-gray-500">No input schema available</div>;
  }

  return (
    <div className={cn("max-h-[60vh] w-full", ...getScrollbarClasses('y'))}>
      <div className="space-y-4 px-4 py-2">
        {Object.entries(schema.properties).map(
          ([name, property]: [string, any]) => {
            const isRequired = schema.required?.includes(name);
            const label = property.title || name;
            const description = property.description;

            return (
              <div
                key={name}
                className="space-y-2"
              >
                <div className="flex items-center justify-between">
                  <Label
                    htmlFor={name}
                    className={cn(
                      isRequired &&
                        "after:ml-0.5 after:text-red-500 after:content-['*']",
                    )}
                  >
                    {_.startCase(label)}
                  </Label>
                  {isRequired && (
                    <span className="text-xs text-gray-500">Required</span>
                  )}
                </div>

                {description && (
                  <p className="text-xs text-gray-500">{description}</p>
                )}

                {renderField(name, property, formValues[name], (value) =>
                  handleChange(name, value),
                )}
              </div>
            );
          },
        )}
      </div>
    </div>
  );
}

function ArrayInputField({
  name,
  property,
  value,
  onChange,
}: {
  name: string;
  property: any;
  value: any[];
  onChange: (value: any[]) => void;
}) {
  const [inputValue, setInputValue] = useState("");
  const [inputError, setInputError] = useState("");

  const arrayItems: ArrayItem[] = (value || []).map((item, index) => ({
    id: `${name}-${index}-${item}`,
    value: item,
  }));

  const itemType = property.items?.type || "string";
  const itemEnum = property.items?.enum;

  const validateAndConvertValue = (input: string): any => {
    const trimmed = input.trim();
    
    if (!trimmed) {
      throw new Error("Please enter a value");
    }

    // If there are enum options, validate against them
    if (itemEnum && !itemEnum.includes(trimmed)) {
      throw new Error(`Value must be one of: ${itemEnum.join(", ")}`);
    }

    switch (itemType) {
      case "number": {
        const num = Number(trimmed);
        if (isNaN(num)) {
          throw new Error("Please enter a valid number");
        }
        return num;
      }
      case "integer": {
        const int = parseInt(trimmed, 10);
        if (isNaN(int) || !Number.isInteger(Number(trimmed))) {
          throw new Error("Please enter a valid integer");
        }
        return int;
      }
      case "boolean": {
        const lower = trimmed.toLowerCase();
        if (lower === "true") return true;
        if (lower === "false") return false;
        throw new Error("Please enter 'true' or 'false'");
      }
      default:
        return trimmed;
    }
  };

  const addItem = () => {
    try {
      const convertedValue = validateAndConvertValue(inputValue);
      
      // Check for duplicates
      const currentValues = value || [];
      if (currentValues.includes(convertedValue)) {
        setInputError("This value has already been added");
        return;
      }

      const newArray = [...currentValues, convertedValue];
      onChange(newArray);
      setInputValue("");
      setInputError("");
    } catch (error: any) {
      setInputError(error.message);
    }
  };

  const removeItem = (itemToRemove: ArrayItem) => {
    const currentValues = value || [];
    const newArray = currentValues.filter((_, index) => {
      const itemId = `${name}-${index}-${currentValues[index]}`;
      return itemId !== itemToRemove.id;
    });
    onChange(newArray);
  };

  const handleInputChange = (newValue: string) => {
    setInputValue(newValue);
    if (inputError) setInputError("");
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addItem();
    }
  };

  const getPlaceholder = () => {
    if (itemEnum) {
      return `Choose from: ${itemEnum.join(", ")}`;
    }
    switch (itemType) {
      case "number":
        return "Enter a number";
      case "integer":
        return "Enter an integer";
      case "boolean":
        return "Enter true or false";
      default:
        return `Enter ${itemType}`;
    }
  };

  return (
    <div className="space-y-4">
      {/* Input Section */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <div className="flex-1">
            {itemEnum ? (
              <Select value={inputValue} onValueChange={handleInputChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an option" />
                </SelectTrigger>
                <SelectContent>
                  {itemEnum.map((option: string) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                placeholder={getPlaceholder()}
                value={inputValue}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyPress={handleKeyPress}
                className={inputError ? "border-red-300 focus:border-red-500" : ""}
                type={itemType === "number" || itemType === "integer" ? "number" : "text"}
                step={itemType === "integer" ? 1 : undefined}
              />
            )}
            {inputError && (
              <p className="text-sm text-red-600 mt-1">{inputError}</p>
            )}
          </div>
          <Button
            onClick={addItem}
            disabled={!inputValue.trim()}
            className="px-6"
            type="button"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        
        {property.items?.description && (
          <p className="text-xs text-muted-foreground italic">
            {property.items.description}
          </p>
        )}
      </div>

      {/* Array Items Display */}
      {arrayItems.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium text-sm text-gray-700">
            Items ({arrayItems.length})
          </h4>
          <div className={cn("space-y-1 max-h-40", ...getScrollbarClasses("y"))}>
            {arrayItems.map((item) => (
              <div 
                key={item.id} 
                className="flex items-start gap-2 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-md transition-all hover:shadow-sm hover:bg-gray-100"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-sm text-foreground break-words">
                    {String(item.value)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeItem(item)}
                  className="flex-shrink-0 h-6 w-6 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {arrayItems.length === 0 && (
        <div className="text-center py-6 border-2 border-dashed border-gray-200 rounded-lg">
          <Plus className="h-8 w-8 text-gray-400 mx-auto mb-2" />
          <h3 className="font-medium text-gray-700 mb-1">No items added yet</h3>
          <p className="text-sm text-gray-500">
            Add {itemType} values to build your array
          </p>
        </div>
      )}
    </div>
  );
}

function renderField(
  name: string,
  property: any,
  value: any,
  onChange: (value: any) => void,
) {
  const type = property.type;

  if (property.enum) {
    return (
      <Select
        value={value || ""}
        onValueChange={onChange}
      >
        <SelectTrigger id={name}>
          <SelectValue placeholder="Select an option" />
        </SelectTrigger>
        <SelectContent>
          {property.enum.map((option: string) => (
            <SelectItem
              key={option}
              value={option}
            >
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  switch (type) {
    case "array":
      return (
        <ArrayInputField
          name={name}
          property={property}
          value={value || []}
          onChange={onChange}
        />
      );

    case "string":
      return (
        <textarea
          id={name}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={property.example || `Enter ${name}`}
          rows={1}
          className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary resize-y min-h-[2.25rem] max-h-40 overflow-auto"
          style={{ resize: 'vertical', overflowWrap: 'break-word', wordBreak: 'break-word' }}
        />
      );

    case "number":
    case "integer": {
      if (property.minimum !== undefined && property.maximum !== undefined) {
        return (
          <div className="space-y-2">
            <Slider
              id={name}
              value={[value || property.minimum]}
              min={property.minimum}
              max={property.maximum}
              step={property.type === "integer" ? 1 : 0.1}
              onValueChange={(vals) => onChange(vals[0])}
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>{property.minimum}</span>
              <span>{value !== undefined ? value : "-"}</span>
              <span>{property.maximum}</span>
            </div>
          </div>
        );
      }

      return (
        <Input
          id={name}
          type="number"
          value={value || ""}
          onChange={(e) => onChange(Number(e.target.value))}
          min={property.minimum}
          max={property.maximum}
          step={property.type === "integer" ? 1 : 0.1}
          placeholder={property.example || `Enter ${name}`}
        />
      );
    }

    case "boolean":
      return (
        <div className="flex items-center space-x-2">
          <Switch
            id={name}
            checked={!!value}
            onCheckedChange={onChange}
          />
          <Label htmlFor={name}>{value ? "Enabled" : "Disabled"}</Label>
        </div>
      );

    case 'object': {
      const objectValue = (value as Record<string, any>) || {}
      return (
        <div className="space-y-4">
          {Object.entries(objectValue).map(
            ([subName, subProperty]: [string, any]) => {
              const isRequired = property.required?.includes(subName);
              const subLabel = subProperty.title || subName;
              const subDescription = subProperty.description;

              return (
                <div
                  key={subName}
                  className="space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <Label
                      htmlFor={subName}
                      className={cn(
                        isRequired &&
                          "after:ml-0.5 after:text-red-500 after:content-['*']",
                      )}
                    >
                      {_.startCase(subLabel)}
                    </Label>
                    {isRequired && (
                      <span className="text-xs text-gray-500">Required</span>
                    )}
                  </div>

                  {subDescription && (
                    <p className="text-xs text-gray-500">{subDescription}</p>
                  )}

                  {renderField(subName, subProperty, objectValue[subName], (value) =>
                    onChange(value),
                  )}
                </div>
              );
            },
          )}
        </div>
      );
    }

    case 'array': {
      const arrayValue = (value as any[]) || []
      return (
        <ArrayInputField
          name={name}
          property={property}
          value={arrayValue}
          onChange={onChange}
        />
      );
    }

    default: {
      const stringValue = value?.toString() || ''
      return (
        <Input
          id={name}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={property.example || `Enter ${name}`}
        />
      );
    }
  }
}
