'use client';

import React, { useEffect, useState } from 'react';
import { GraphSchema } from '@/types/graph';
import { cn } from '@/lib/utils';

interface GraphVisualizationProps {
  schema: GraphSchema;
  className?: string;
}

function convertToCytoscape(schema: GraphSchema): Array<{ data: any; classes: string }> {
  const elements: Array<{ data: any; classes: string }> = [];
  
  // Group nodes by subgraph FIRST
  const mainNodes: string[] = [];
  const subgraphGroups = new Map<string, string[]>();
  
  schema.nodes.forEach(node => {
    if (node.id.includes(':')) {
      const subgraphName = node.id.split(':')[0];
      if (!subgraphGroups.has(subgraphName)) {
        subgraphGroups.set(subgraphName, []);
      }
      subgraphGroups.get(subgraphName)!.push(node.id);
    } else {
      mainNodes.push(node.id);
    }
  });

  // Add main nodes
  mainNodes.forEach(node => {
    const nodeData = schema.nodes.find(n => n.id === node);
    let label = nodeData?.data?.name || node;
    
    // Clean up labels
    if (node === '__start__') label = 'Start';
    if (node === '__end__') label = 'End';
    label = label.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    
    // Determine node class for styling
    let nodeClass = 'regular';
    if (node === '__start__' || node === '__end__') nodeClass = 'startEnd';
    if (label.toLowerCase().includes('decision') || label.toLowerCase().includes('feedback')) nodeClass = 'decision';
    
    elements.push({
      data: { 
        id: node, 
        label: label
      },
      classes: nodeClass
    });
  });

  // Add compound nodes for subgraphs
  subgraphGroups.forEach((nodes, subgraphName) => {
    // Create parent container
    elements.push({
      data: { 
        id: subgraphName,
        label: subgraphName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
      },
      classes: 'subgraph-container'
    });

    // Add child nodes WITH parent reference
    nodes.forEach(nodeId => {
      // Extract only the node name part (after the colon)
      let label = nodeId.split(':').pop() || nodeId;
      label = label.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      
      elements.push({
        data: { 
          id: nodeId,
          label: label,
          parent: subgraphName  // This makes it a child of the container
        },
        classes: 'subgraph-child'
      });
    });
  });
  
  // Convert edges
  schema.edges.forEach(edge => {
    elements.push({
      data: { 
        source: edge.source, 
        target: edge.target,
        conditional: edge.conditional 
      },
      classes: edge.conditional ? 'conditional' : 'regular'
    });
  });
  
  return elements;
}

export function GraphVisualization({ schema, className }: GraphVisualizationProps) {
  const [CytoscapeComponent, setCytoscapeComponent] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadCytoscape = async () => {
      try {
        const [
          { default: Cytoscape },
          { default: dagre },
          { default: CytoscapeComponentImport }
        ] = await Promise.all([
          import('cytoscape'),
          import('cytoscape-dagre'),
          import('react-cytoscapejs')
        ]);

        // Register the dagre layout - ESLint incorrectly thinks this is a React hook
        // eslint-disable-next-line react-hooks/rules-of-hooks
        Cytoscape.use(dagre);
        
        setCytoscapeComponent(() => CytoscapeComponentImport);
        setIsLoading(false);
      } catch (error) {
        console.error('Failed to load Cytoscape:', error);
        setIsLoading(false);
      }
    };

    loadCytoscape();
  }, []);

  if (isLoading) {
    return (
      <div className={cn(
        "w-full h-full",
        "rounded-lg",
        "bg-gray-50",
        "shadow-sm",
        "flex items-center justify-center",
        className
      )}>
        <div className="text-gray-500">Loading graph visualization...</div>
      </div>
    );
  }

  if (!CytoscapeComponent) {
    return (
      <div className={cn(
        "w-full h-full",
        "rounded-lg",
        "bg-gray-50",
        "shadow-sm",
        "flex items-center justify-center",
        className
      )}>
        <div className="text-red-500">Failed to load graph visualization</div>
      </div>
    );
  }

  const elements = convertToCytoscape(schema);
  
  const layout = {
    name: 'dagre',
    rankDir: 'TB',           // Top to bottom
    spacingFactor: 1.5,      // Increase for more space
    nodeDimensionsIncludeLabels: true,
    rankSep: 20,             // More vertical spacing
    nodeSep: 100,            // Reduce horizontal spacing
    edgeSep: 20,             // Tighter edge separation
    marginx: 60,
    marginy: 60,
    fit: true,
    padding: 60
  };
  
  const stylesheet = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'shape': 'round-rectangle',
        'background-color': '#f8fafc',
        'border-width': 1,
        'border-color': '#d1d5db',
        'width': '200px',
        'height': '60px',
        'font-size': '14px',
        'font-family': 'system-ui, -apple-system, sans-serif',
        'font-weight': '400',
        'color': '#374151',
        'text-valign': 'center',
        'text-halign': 'center',
        'text-wrap': 'wrap',
        'text-max-width': '180px'
      }
    },
    {
      selector: 'node[id="__start__"]',
      style: {
        'background-color': '#dcfce7',
        'border-color': '#16a34a',
        'border-width': 2,
        'font-weight': '500',
        'color': '#166534'
      }
    },
    {
      selector: 'node[id="__end__"]',
      style: {
        'background-color': '#dbeafe',
        'border-color': '#2563eb',
        'border-width': 2,
        'font-weight': '500',
        'color': '#1e40af'
      }
    },
    {
      selector: '.regular',
      style: {
        'background-color': '#ffffff',
        'border-color': '#d1d5db'
      }
    },
    {
      selector: '.decision',
      style: {
        'background-color': '#fef3c7',
        'border-color': '#f59e0b',
        'border-width': 1
      }
    },
    {
      selector: '.subgraph-container',
      style: {
        'background-color': 'transparent',
        'background-opacity': 0,
        'border-color': '#3b82f6',
        'border-width': 2,
        'border-style': 'dashed',
        'border-opacity': 0.6,
        'font-size': '12px',
        'font-weight': '500',
        'color': '#3b82f6',
        'text-valign': 'top',
        'text-halign': 'left',
        'text-margin-y': '-10px',
        'padding': '20px'
      }
    },
    {
      selector: '.subgraph-child',
      style: {
        'background-color': '#ffffff',
        'border-color': '#d1d5db'
      }
    },
    {
      selector: 'edge',
      style: {
        'curve-style': 'straight',
        'edge-distances': 'node-position',
        'source-distance-from-node': '5px',
        'target-distance-from-node': '5px',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#6b7280',
        'line-color': '#6b7280'
      }
    },
    {
      selector: 'edge[source="human_feedback"][target="generate_report_plan"]',
      style: {
        'curve-style': 'bezier',
        'control-point-step-size': 40
      }
    },
    {
      selector: '.conditional',
      style: {
        'line-style': 'dashed',
        'curve-style': 'bezier',
        'control-point-step-size': 40
      }
    }
  ];
  
  return (
    <div className={cn(
      "w-full h-full",
      "rounded-lg",
      "bg-gray-50",
      "shadow-sm",
      className
    )}>
      <CytoscapeComponent
        elements={elements}
        layout={layout}
        stylesheet={stylesheet}
        style={{ 
          width: '100%', 
          height: '100%', 
          minHeight: '500px',
          backgroundColor: '#ffffff'
        }}
        cy={(cy: any) => {
          // Enable zooming and panning
          cy.userZoomingEnabled(true);
          cy.userPanningEnabled(true);
          cy.boxSelectionEnabled(false);
          
          // Better zoom limits - allow much more zoom out
          cy.minZoom(0.1);
          cy.maxZoom(2.0);
          
          // Fit to container on load
          cy.ready(() => {
            cy.fit(undefined, 100);     // More padding
            cy.center();
            cy.zoom(0.9);               // Start less zoomed out
          });
        }}
      />
    </div>
  );
} 