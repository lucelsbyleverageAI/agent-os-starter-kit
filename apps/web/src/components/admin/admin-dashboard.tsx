"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { PublicPermissionTable } from "./public-permission-table";
import { RevokePermissionModal } from "./revoke-permission-modal";
import { AddPermissionModal } from "./add-permission-modal";
import { PublicGraphPermission, PublicAssistantPermission, PublicCollectionPermission, PublicSkillPermission } from "@/types/public-permissions";
import { useAuthContext } from "@/providers/Auth";
import {
  getPublicGraphs,
  getPublicAssistants,
  getPublicCollections,
  getPublicSkills,
  revokePublicGraph,
  revokePublicAssistant,
  revokePublicCollection,
  revokePublicSkill,
  createPublicGraph,
  createPublicAssistant,
  createPublicCollection,
  createPublicSkill,
  reinvokePublicGraph,
  reinvokePublicAssistant,
  reinvokePublicCollection,
  reinvokePublicSkill,
  getAllCollectionsForAdmin,
  getAllSkillsForAdmin
} from "@/lib/public-permissions-client";
import { toast } from "sonner";
import { useAgentsContext } from "@/providers/Agents";
import { Collection } from "@/types/collection";
import { Skill } from "@/types/skill";
import { RetiredGraphsTable } from "./retired-graphs-table";

// Use discriminated union type to avoid TypeScript conflicts
type Permission =
  | (PublicGraphPermission & { _type: 'graph' })
  | (PublicAssistantPermission & { _type: 'assistant' })
  | (PublicCollectionPermission & { _type: 'collection' })
  | (PublicSkillPermission & { _type: 'skill' });

export const AdminDashboard = () => {
  const { session } = useAuthContext();
  const { displayItems: agentDisplayItems, discoveryData } = useAgentsContext();
  const graphNameById = useMemo(() => {
    const map: Record<string, string> = {};
    const graphs = discoveryData?.valid_graphs || [];
    for (const g of graphs) {
      if (g?.name) map[g.graph_id] = g.name;
    }
    return map;
  }, [discoveryData?.valid_graphs]);
  
  const [selectedItem, setSelectedItem] = useState<Permission | null>(null);
  const [actionType, setActionType] = useState<'revoke' | 're_invoke' | 'revoke_all'>('revoke');
  const [showAddModal, setShowAddModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'graph' | 'assistant' | 'collection' | 'skill'>('graph');

  const [graphs, setGraphs] = useState<PublicGraphPermission[]>([]);
  const [assistants, setAssistants] = useState<PublicAssistantPermission[]>([]);
  const [collections_permissions, setCollectionsPermissions] = useState<PublicCollectionPermission[]>([]);
  const [skills_permissions, setSkillsPermissions] = useState<PublicSkillPermission[]>([]);
  const [adminCollections, setAdminCollections] = useState<Collection[]>([]);
  const [adminSkills, setAdminSkills] = useState<Skill[]>([]);

  const [isLoadingGraphs, setIsLoadingGraphs] = useState(true);
  const [isLoadingAssistants, setIsLoadingAssistants] = useState(true);
  const [isLoadingCollections, setIsLoadingCollections] = useState(true);
  const [isLoadingSkills, setIsLoadingSkills] = useState(true);
  const [_isLoadingAdminCollections, setIsLoadingAdminCollections] = useState(true);
  const [_isLoadingAdminSkills, setIsLoadingAdminSkills] = useState(true);
  const [isRevokingPermission, setIsRevokingPermission] = useState(false);
  const [isAddingPermission, setIsAddingPermission] = useState(false);

  const assistantNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    agentDisplayItems.forEach(item => {
      if (item.type === 'assistant' && item.assistant_id) {
        map[item.assistant_id] = item.name;
      }
    });
    return map;
  }, [agentDisplayItems]);

  const collectionNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    adminCollections.forEach((collection: Collection) => {
      map[collection.uuid] = collection.name;
    });
    return map;
  }, [adminCollections]);

  const skillNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    adminSkills.forEach((skill: Skill) => {
      map[skill.id] = skill.name;
    });
    return map;
  }, [adminSkills]);

  // Enrich collections permissions with display names
  const enrichedCollectionsPermissions = useMemo(() => {
    return collections_permissions.map(collection => ({
      ...collection,
      collection_display_name: collectionNameMap[collection.collection_id] || 'Unknown Collection',
    }));
  }, [collections_permissions, collectionNameMap]);

  // Enrich skills permissions with display names
  const enrichedSkillsPermissions = useMemo(() => {
    return skills_permissions.map(skill => ({
      ...skill,
      skill_display_name: skillNameMap[skill.skill_id] || 'Unknown Skill',
    }));
  }, [skills_permissions, skillNameMap]);

  const fetchGraphs = useCallback(async () => {
    if (!session?.accessToken) return;

    try {
      setIsLoadingGraphs(true);
      const data = await getPublicGraphs(session.accessToken);

      // Enrich with display names: prefer saved name, fallback to graph_id
      const enrichedData = data.map(graph => ({
        ...graph,
        graph_display_name: graphNameById[graph.graph_id] || graph.graph_id,
      }));

      setGraphs(enrichedData);
    } catch (error) {
      console.error("Failed to fetch public graphs:", error);
      toast.error("Failed to load public graphs");
    } finally {
      setIsLoadingGraphs(false);
    }
  }, [session?.accessToken, graphNameById]);

  const fetchAssistants = useCallback(async () => {
    if (!session?.accessToken) return;
    
    try {
      setIsLoadingAssistants(true);
      const data = await getPublicAssistants(session.accessToken);
      
      // Enrich with display names
      const enrichedData = data.map(assistant => ({
        ...assistant,
        assistant_display_name: assistantNameMap[assistant.assistant_id] || 'Unknown Assistant',
      }));
      
      setAssistants(enrichedData);
    } catch (error) {
      console.error("Failed to fetch public assistants:", error);
      toast.error("Failed to load public assistants");
    } finally {
      setIsLoadingAssistants(false);
    }
  }, [session?.accessToken, assistantNameMap]);

  const fetchAdminCollections = useCallback(async () => {
    if (!session?.accessToken) return;
    
    try {
      setIsLoadingAdminCollections(true);
      const data = await getAllCollectionsForAdmin(session.accessToken);
      setAdminCollections(data);
    } catch (error) {
      console.error("Failed to fetch admin collections:", error);
      toast.error("Failed to load admin collections");
    } finally {
      setIsLoadingAdminCollections(false);
    }
  }, [session?.accessToken]);

  const fetchCollections = useCallback(async () => {
    if (!session?.accessToken) return;

    try {
      setIsLoadingCollections(true);
      const data = await getPublicCollections(session.accessToken);
      setCollectionsPermissions(data);
    } catch (error) {
      console.error("Failed to fetch public collections:", error);
      toast.error("Failed to load public collections");
    } finally {
      setIsLoadingCollections(false);
    }
  }, [session?.accessToken]);

  const fetchAdminSkills = useCallback(async () => {
    if (!session?.accessToken) return;

    try {
      setIsLoadingAdminSkills(true);
      const data = await getAllSkillsForAdmin(session.accessToken);
      setAdminSkills(data);
    } catch (error) {
      console.error("Failed to fetch admin skills:", error);
      toast.error("Failed to load admin skills");
    } finally {
      setIsLoadingAdminSkills(false);
    }
  }, [session?.accessToken]);

  const fetchSkills = useCallback(async () => {
    if (!session?.accessToken) return;

    try {
      setIsLoadingSkills(true);
      const data = await getPublicSkills(session.accessToken);
      setSkillsPermissions(data);
    } catch (error) {
      console.error("Failed to fetch public skills:", error);
      toast.error("Failed to load public skills");
    } finally {
      setIsLoadingSkills(false);
    }
  }, [session?.accessToken]);

  // Combined refresh function to keep all tables synchronized
  const refreshAllData = useCallback(async () => {
    await Promise.all([fetchGraphs(), fetchAssistants(), fetchCollections(), fetchAdminCollections(), fetchSkills(), fetchAdminSkills()]);
  }, [fetchGraphs, fetchAssistants, fetchCollections, fetchAdminCollections, fetchSkills, fetchAdminSkills]);

  useEffect(() => {
    refreshAllData();
  }, [refreshAllData]);

  // Type-safe handlers using discriminated union
  const handleRevokeItem = (item: PublicGraphPermission | PublicAssistantPermission | PublicCollectionPermission | PublicSkillPermission, action: 'revoke' | 're_invoke' | 'revoke_all' = 'revoke') => {
    let typedItem: Permission;

    if ('graph_id' in item) {
      typedItem = { ...item, _type: 'graph' as const };
    } else if ('assistant_id' in item) {
      typedItem = { ...item, _type: 'assistant' as const };
    } else if ('collection_id' in item) {
      typedItem = { ...item, _type: 'collection' as const };
    } else {
      typedItem = { ...item, _type: 'skill' as const };
    }

    setSelectedItem(typedItem);
    setActionType(action);
  };

  const handleRevokeConfirm = async (mode: 'revoke_all' | 'future_only') => {
    if (!selectedItem || !session?.accessToken) return;

    try {
      setIsRevokingPermission(true);
      
      if (actionType === 're_invoke') {
        // Handle re-invoke action
        switch (selectedItem._type) {
          case 'graph':
            await reinvokePublicGraph({
              graphId: selectedItem.graph_id,
              accessToken: session.accessToken,
            });
            toast.success("Public graph permission re-invoked successfully");
            break;
          case 'assistant':
            await reinvokePublicAssistant({
              assistantId: selectedItem.assistant_id,
              accessToken: session.accessToken,
            });
            toast.success("Public assistant permission re-invoked successfully");
            break;
          case 'collection':
            await reinvokePublicCollection({
              collectionId: selectedItem.collection_id,
              accessToken: session.accessToken,
            });
            toast.success("Public collection permission re-invoked successfully");
            break;
          case 'skill':
            await reinvokePublicSkill({
              skillId: selectedItem.skill_id,
              accessToken: session.accessToken,
            });
            toast.success("Public skill permission re-invoked successfully");
            break;
        }
      } else {
        // Handle revoke actions
        switch (selectedItem._type) {
          case 'graph':
            await revokePublicGraph({
              id: selectedItem.graph_id,
              revokeMode: actionType === 'revoke_all' ? 'revoke_all' : mode,
              accessToken: session.accessToken,
            });
            toast.success("Public graph permission revoked successfully");
            break;
          case 'assistant':
            await revokePublicAssistant({
              id: selectedItem.assistant_id,
              revokeMode: actionType === 'revoke_all' ? 'revoke_all' : mode,
              accessToken: session.accessToken,
            });
            toast.success("Public assistant permission revoked successfully");
            break;
          case 'collection':
            await revokePublicCollection({
              id: selectedItem.collection_id,
              revokeMode: actionType === 'revoke_all' ? 'revoke_all' : mode,
              accessToken: session.accessToken,
            });
            toast.success("Public collection permission revoked successfully");
            break;
          case 'skill':
            await revokePublicSkill({
              id: selectedItem.skill_id,
              revokeMode: actionType === 'revoke_all' ? 'revoke_all' : mode,
              accessToken: session.accessToken,
            });
            toast.success("Public skill permission revoked successfully");
            break;
        }
      }
      
      // Always refresh all tables since permissions might be linked
      await refreshAllData();
    } catch (error: any) {
      console.error('Error processing permission action:', error);
      toast.error(error.message || 'Failed to process permission action');
    } finally {
      setIsRevokingPermission(false);
      setSelectedItem(null);
    }
  };

  const handleAddPermission = async (type: 'graph' | 'assistant' | 'collection' | 'skill', id: string, permissionLevel: string) => {
    if (!session?.accessToken) return;

    try {
      setIsAddingPermission(true);

      switch (type) {
        case 'graph':
          await createPublicGraph({
            graphId: id,
            permissionLevel: permissionLevel as 'access' | 'admin',
            accessToken: session.accessToken,
          });
          toast.success("Public graph permission created successfully");
          break;
        case 'assistant':
          await createPublicAssistant({
            assistantId: id,
            permissionLevel: permissionLevel as 'viewer' | 'editor',
            accessToken: session.accessToken,
          });
          toast.success("Public assistant permission created successfully");
          break;
        case 'collection':
          await createPublicCollection({
            collectionId: id,
            permissionLevel: permissionLevel as 'viewer' | 'editor',
            accessToken: session.accessToken,
          });
          toast.success("Public collection permission created successfully");
          break;
        case 'skill':
          await createPublicSkill({
            skillId: id,
            permissionLevel: permissionLevel as 'viewer' | 'editor',
            accessToken: session.accessToken,
          });
          toast.success("Public skill permission created successfully");
          break;
      }

      await refreshAllData();
      setShowAddModal(false);
    } catch (error) {
      console.error("Failed to create permission:", error);
      toast.error("Failed to create permission");
    } finally {
      setIsAddingPermission(false);
    }
  };

  return (
    <>
      <Tabs defaultValue="graphs" className="w-full" onValueChange={(value) => {
        // Map plural tab values to singular forms for the modal
        const tabMap: Record<string, 'graph' | 'assistant' | 'collection' | 'skill'> = {
          'graphs': 'graph',
          'assistants': 'assistant',
          'collections': 'collection',
          'skills': 'skill'
        };
        setActiveTab(tabMap[value] || 'graph');
      }}>
        <TabsList variant="branded">
          <TabsTrigger value="graphs">
            Public Graphs
          </TabsTrigger>
          <TabsTrigger value="assistants">
            Public Assistants
          </TabsTrigger>
          <TabsTrigger value="collections">
            Public Collections
          </TabsTrigger>
          <TabsTrigger value="skills">
            Public Skills
          </TabsTrigger>
          <TabsTrigger value="retired">
            Retired Agents
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="graphs" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>Public Graph Permissions</CardTitle>
                <CardDescription>
                  Manage graphs that are automatically accessible to all users
                </CardDescription>
              </div>
              <Button 
                onClick={() => {
                  setShowAddModal(true);
                }}
                size="sm"
                className="ml-auto"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Graph Permission
              </Button>
            </CardHeader>
            <CardContent>
              <PublicPermissionTable
                data={graphs}
                onRevoke={handleRevokeItem}
                isLoading={isLoadingGraphs}
                type="graph"
              />
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="assistants" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>Public Assistant Permissions</CardTitle>
                <CardDescription>
                  Manage assistants that are automatically accessible to all users
                </CardDescription>
              </div>
              <Button 
                onClick={() => {
                  setShowAddModal(true);
                }}
                size="sm"
                className="ml-auto"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Assistant Permission
              </Button>
            </CardHeader>
            <CardContent>
              <PublicPermissionTable
                data={assistants}
                onRevoke={handleRevokeItem}
                isLoading={isLoadingAssistants}
                type="assistant"
              />
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="collections" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>Public Collection Permissions</CardTitle>
                <CardDescription>
                  Manage collections that are automatically accessible to all users
                </CardDescription>
              </div>
              <Button 
                onClick={() => {
                  setShowAddModal(true);
                }}
                size="sm"
                className="ml-auto"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Collection Permission
              </Button>
            </CardHeader>
            <CardContent>
              <PublicPermissionTable
                data={enrichedCollectionsPermissions}
                onRevoke={handleRevokeItem}
                isLoading={isLoadingCollections}
                type="collection"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="skills" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>Public Skill Permissions</CardTitle>
                <CardDescription>
                  Manage skills that are automatically accessible to all users
                </CardDescription>
              </div>
              <Button
                onClick={() => {
                  setShowAddModal(true);
                }}
                size="sm"
                className="ml-auto"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Skill Permission
              </Button>
            </CardHeader>
            <CardContent>
              <PublicPermissionTable
                data={enrichedSkillsPermissions}
                onRevoke={handleRevokeItem}
                isLoading={isLoadingSkills}
                type="skill"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="retired" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>Retired Agents</CardTitle>
                <CardDescription>
                  Manually prune or unretire agents/graphs marked as unavailable
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <RetiredGraphsTable />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Revoke Permission Modal */}
      <RevokePermissionModal
        item={selectedItem}
        isOpen={!!selectedItem}
        onClose={() => setSelectedItem(null)}
        onConfirm={handleRevokeConfirm}
        isLoading={isRevokingPermission}
        actionType={actionType}
      />

      {/* Add Permission Modal */}
      <AddPermissionModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onConfirm={handleAddPermission}
        isLoading={isAddingPermission}
        type={activeTab}
        existingGraphPermissions={graphs}
        existingAssistantPermissions={assistants}
        existingCollectionPermissions={enrichedCollectionsPermissions}
        existingSkillPermissions={enrichedSkillsPermissions}
        allSkills={adminSkills}
      />
    </>
  );
}; 