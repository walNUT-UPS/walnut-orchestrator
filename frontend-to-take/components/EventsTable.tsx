import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import { Button } from './ui/button';
import { Tag } from './Tag';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { cn } from './ui/utils';

export interface Event {
  id: string;
  timestamp: string;
  type: 'OnBattery' | 'LowBattery' | 'Recovered' | 'Shutdown' | 'Test' | 'ConnectionLost';
  source: 'UPS' | 'Host' | 'Policy';
  severity: 'Info' | 'Warning' | 'Critical';
  message: string;
  payload?: Record<string, any>;
  relatedHost?: string;
}

interface EventsTableProps {
  events: Event[];
  onRowClick?: (event: Event) => void;
}

const severityConfig = {
  Info: { variant: 'info' as const },
  Warning: { variant: 'warn' as const },
  Critical: { variant: 'error' as const }
};

const typeConfig = {
  OnBattery: { variant: 'warn' as const },
  LowBattery: { variant: 'error' as const },
  Recovered: { variant: 'ok' as const },
  Shutdown: { variant: 'error' as const },
  Test: { variant: 'info' as const },
  ConnectionLost: { variant: 'error' as const }
};

export function EventsTable({ events, onRowClick }: EventsTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (eventId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(eventId)) {
      newExpanded.delete(eventId);
    } else {
      newExpanded.add(eventId);
    }
    setExpandedRows(newExpanded);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  };

  if (events.length === 0) {
    return (
      <div className="card-standard p-12 text-center">
        <div className="text-body text-muted-foreground mb-2">No events found</div>
        <div className="text-micro text-muted-foreground">
          Events will appear here as they occur
        </div>
      </div>
    );
  }

  return (
    <div className="card-standard overflow-hidden">
      <Table>
        <TableHeader className="bg-muted/30">
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12"></TableHead>
            <TableHead className="text-right min-w-[160px]">Timestamp</TableHead>
            <TableHead className="text-left">Type</TableHead>
            <TableHead className="text-left">Source</TableHead>
            <TableHead className="text-left">Severity</TableHead>
            <TableHead className="text-left">Message</TableHead>
            <TableHead className="text-center w-24">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => {
            const isExpanded = expandedRows.has(event.id);
            const typeVariant = typeConfig[event.type];
            const severityVariant = severityConfig[event.severity];
            
            return (
              <Collapsible key={event.id} open={isExpanded} onOpenChange={() => toggleRow(event.id)}>
                <CollapsibleTrigger asChild>
                  <TableRow className={cn(
                    "cursor-pointer hover:bg-accent/30 transition-colors",
                    "h-12" // 48px row height as specified
                  )}>
                    <TableCell className="text-center">
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 focus-ring">
                        {isExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                      </Button>
                    </TableCell>
                    <TableCell className="font-mono text-micro tabular-nums text-right">
                      {formatTimestamp(event.timestamp)}
                    </TableCell>
                    <TableCell className="text-left">
                      <Tag variant={typeVariant.variant} size="sm">
                        {event.type}
                      </Tag>
                    </TableCell>
                    <TableCell className="text-left">
                      <span className="text-micro text-muted-foreground">{event.source}</span>
                    </TableCell>
                    <TableCell className="text-left">
                      <Tag variant={severityVariant.variant} size="sm">
                        {event.severity}
                      </Tag>
                    </TableCell>
                    <TableCell className="text-left max-w-md">
                      <div className="truncate" title={event.message}>
                        {event.message}
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      {event.relatedHost && (
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="h-6 text-xs focus-ring"
                          onClick={(e) => {
                            e.stopPropagation();
                            // Handle related host navigation
                          }}
                        >
                          <ExternalLink className="w-3 h-3 mr-1" />
                          Host
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                </CollapsibleTrigger>
                
                {event.payload && (
                  <CollapsibleContent asChild>
                    <TableRow>
                      <TableCell colSpan={7} className="bg-muted/10 border-t border-border">
                        <div className="p-4 space-y-2">
                          <div className="text-micro text-muted-foreground mb-2">Event Payload:</div>
                          <pre className="bg-background p-3 rounded-md text-xs overflow-x-auto border border-border font-mono">
                            {JSON.stringify(event.payload, null, 2)}
                          </pre>
                        </div>
                      </TableCell>
                    </TableRow>
                  </CollapsibleContent>
                )}
              </Collapsible>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}