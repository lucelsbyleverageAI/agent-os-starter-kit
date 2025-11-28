"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { PublicGraphPermission, PublicAssistantPermission, PublicCollectionPermission, PublicSkillPermission } from "@/types/public-permissions";
import { Badge } from "@/components/ui/badge";

type Permission = PublicGraphPermission | PublicAssistantPermission | PublicCollectionPermission | PublicSkillPermission;

interface PublicPermissionTableProps<T extends Permission> {
  data: T[];
  onRevoke: (item: T, action?: 'revoke' | 're_invoke' | 'revoke_all') => void;
  isLoading: boolean;
  type: 'graph' | 'assistant' | 'collection' | 'skill';
}

export const PublicPermissionTable = <T extends Permission>({
  data,
  onRevoke,
  isLoading,
  type,
}: PublicPermissionTableProps<T>) => {
  const renderCell = (item: T, accessor: string) => {
    switch (accessor) {
      case "id":
        if ('graph_id' in item) {
          return (
            <div className="flex flex-col">
              <span className="font-medium">{item.graph_display_name || 'N/A'}</span>
              <span className="text-sm text-muted-foreground">{item.graph_id}</span>
            </div>
          );
        } else if ('assistant_id' in item) {
          return (
            <div className="flex flex-col">
              <span className="font-medium">{item.assistant_display_name || 'N/A'}</span>
              <span className="text-sm text-muted-foreground">{item.assistant_id}</span>
            </div>
          );
        } else if ('collection_id' in item) {
          return (
            <div className="flex flex-col">
              <span className="font-medium">{item.collection_display_name || 'N/A'}</span>
              <span className="text-sm text-muted-foreground">{item.collection_id}</span>
            </div>
          );
        } else if ('skill_id' in item) {
          return (
            <div className="flex flex-col">
              <span className="font-medium">{item.skill_display_name || 'N/A'}</span>
              <span className="text-sm text-muted-foreground">{item.skill_id}</span>
            </div>
          );
        }
        return null;
      case "permission_level": {
        const isRevoked = item.revoked_at !== null;
        return (
          <div className="flex items-center gap-2">
            <Badge 
              variant={isRevoked ? "outline" : "secondary"} 
              className={isRevoked ? 'text-muted-foreground' : ''}
            >
              {item.permission_level}
            </Badge>
            {isRevoked && (
              <div className="flex items-center gap-1">
                <Badge variant="destructive" className="text-xs">
                  Revoked
                </Badge>
                {item.revoke_mode && (
                  <Badge 
                    variant="outline" 
                    className={`text-xs ${
                      item.revoke_mode === 'revoke_all' 
                        ? 'border-red-200 text-red-700' 
                        : 'border-orange-200 text-orange-700'
                    }`}
                  >
                    {item.revoke_mode === 'revoke_all' ? 'All Users' : 'Future Only'}
                  </Badge>
                )}
              </div>
            )}
          </div>
        );
      }
      case "created_by": {
        const isRevoked = item.revoked_at !== null;
        return (
          <span className={`text-sm ${isRevoked ? 'opacity-60' : ''}`}>
            {item.created_by || 'Unknown'}
          </span>
        );
      }
      case "created_at": {
        const isRevoked = item.revoked_at !== null;
        return (
          <div className={`text-sm ${isRevoked ? 'opacity-60' : ''}`}>
            <div>
              {item.created_at ? new Date(item.created_at).toLocaleDateString() : 'N/A'}
            </div>
            {isRevoked && (
              <div className="text-xs text-muted-foreground">
                Revoked: {new Date(item.revoked_at!).toLocaleDateString()}
                {item.revoke_mode && (
                  <span className="ml-1">
                    ({item.revoke_mode === 'revoke_all' ? 'all users' : 'future only'})
                  </span>
                )}
              </div>
            )}
          </div>
        );
      }
      case "actions": {
        const isRevoked = item.revoked_at !== null;
        
        if (isRevoked) {
          return (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRevoke(item, 're_invoke')}
                disabled={isLoading}
              >
                Re-invoke
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => onRevoke(item, 'revoke_all')}
                disabled={isLoading}
              >
                Revoke All
              </Button>
            </div>
          );
        }
        
        return (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onRevoke(item, 'revoke')}
            disabled={isLoading}
          >
            Revoke
          </Button>
        );
      }
      default:
        return null;
    }
  };

  const getHeaderLabel = () => {
    switch (type) {
      case 'graph': return 'Graph';
      case 'assistant': return 'Assistant';
      case 'collection': return 'Collection';
      case 'skill': return 'Skill';
    }
  };

  const headers = [
    { key: "id", label: getHeaderLabel() },
    { key: "permission_level", label: "Permission Level" },
    { key: "created_by", label: "Created By" },
    { key: "created_at", label: "Created At" },
    { key: "actions", label: "Actions" },
  ];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-sm text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-sm text-muted-foreground">
          No public {type} permissions found.
        </div>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {headers.map((header) => (
            <TableHead key={header.key}>{header.label}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((item) => {
          let key: string;
          if ('graph_id' in item) {
            key = `graph-${item.id}-${item.graph_id}`;
          } else if ('assistant_id' in item) {
            key = `assistant-${item.id}-${item.assistant_id}`;
          } else if ('collection_id' in item) {
            key = `collection-${item.id}-${item.collection_id}`;
          } else {
            // Must be skill since we have a union of exactly these four types
            key = `skill-${item.id}-${(item as PublicSkillPermission).skill_id}`;
          }
          
          return (
            <TableRow key={key}>
              {headers.map((header) => (
                <TableCell key={header.key}>
                  {renderCell(item, header.key)}
                </TableCell>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}; 