import React, { useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Switch } from "./ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Badge } from "./ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { ScrollArea } from "./ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./ui/collapsible";
import {
  AlertCircle,
  CheckCircle2,
  GripVertical,
  Plus,
  X,
  ChevronDown,
  ExternalLink,
  Zap,
} from "lucide-react";
import { DndProvider, useDrag, useDrop } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";

interface PolicyEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface Action {
  id: string;
  integration: string;
  capability: string;
  verb: string;
  concurrency: number;
  backoff: number;
  timeout: number;
  dryRun: boolean;
}

interface DragItem {
  index: number;
  id: string;
  type: string;
}

const ActionItem: React.FC<{
  action: Action;
  index: number;
  moveAction: (dragIndex: number, hoverIndex: number) => void;
  updateAction: (
    index: number,
    field: keyof Action,
    value: any,
  ) => void;
  removeAction: (index: number) => void;
}> = ({
  action,
  index,
  moveAction,
  updateAction,
  removeAction,
}) => {
  const [{ isDragging }, drag] = useDrag({
    type: "action",
    item: () => ({
      id: action.id,
      index,
      type: "action",
    }),
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  const [, drop] = useDrop({
    accept: "action",
    hover(item: DragItem) {
      if (!item) {
        return;
      }
      const dragIndex = item.index;
      const hoverIndex = index;

      if (dragIndex === hoverIndex) {
        return;
      }

      moveAction(dragIndex, hoverIndex);
      item.index = hoverIndex;
    },
  });

  const ref = React.useRef<HTMLDivElement>(null);
  drag(drop(ref));

  return (
    <div
      ref={ref}
      className={`transition-all ${isDragging ? "opacity-50 scale-95" : ""}`}
    >
      <Card className="shadow-sm">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <div className="mt-1 cursor-move text-slate-400 hover:text-slate-600">
              <GripVertical className="h-4 w-4" />
            </div>
            <div className="flex-1 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Integration
                  </Label>
                  <Select
                    value={action.integration}
                    onValueChange={(value) =>
                      updateAction(index, "integration", value)
                    }
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select integration" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tapo">
                        Tapo Smart Plugs
                      </SelectItem>
                      <SelectItem value="kasa">
                        Kasa Smart Home
                      </SelectItem>
                      <SelectItem value="slack">Slack</SelectItem>
                      <SelectItem value="email">Email</SelectItem>
                      <SelectItem value="webhook">
                        Webhook
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Capability
                  </Label>
                  <Select
                    value={action.capability}
                    onValueChange={(value) =>
                      updateAction(index, "capability", value)
                    }
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select capability" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="power.control">
                        Power Control
                      </SelectItem>
                      <SelectItem value="notify">
                        Notify
                      </SelectItem>
                      <SelectItem value="host.shutdown">
                        Host Shutdown
                      </SelectItem>
                      <SelectItem value="alert">Alert</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Verb
                  </Label>
                  <Select
                    value={action.verb}
                    onValueChange={(value) =>
                      updateAction(index, "verb", value)
                    }
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select verb" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="shutdown">
                        Shutdown
                      </SelectItem>
                      <SelectItem value="send">Send</SelectItem>
                      <SelectItem value="turn_off">
                        Turn Off
                      </SelectItem>
                      <SelectItem value="turn_on">
                        Turn On
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end">
                  <div className="flex items-center space-x-2">
                    <Switch
                      id={`dry-run-${action.id}`}
                      checked={action.dryRun}
                      onCheckedChange={(checked) =>
                        updateAction(index, "dryRun", checked)
                      }
                    />
                    <Label
                      htmlFor={`dry-run-${action.id}`}
                      className="text-sm"
                    >
                      Dry Run
                    </Label>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Concurrency
                  </Label>
                  <Input
                    type="number"
                    value={action.concurrency}
                    onChange={(e) =>
                      updateAction(
                        index,
                        "concurrency",
                        parseInt(e.target.value),
                      )
                    }
                    className="mt-1"
                    min="1"
                    max="50"
                  />
                </div>
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Backoff (ms)
                  </Label>
                  <Input
                    type="number"
                    value={action.backoff}
                    onChange={(e) =>
                      updateAction(
                        index,
                        "backoff",
                        parseInt(e.target.value),
                      )
                    }
                    className="mt-1"
                    min="0"
                    step="100"
                  />
                </div>
                <div>
                  <Label className="text-sm font-medium text-slate-700">
                    Timeout (s)
                  </Label>
                  <Input
                    type="number"
                    value={action.timeout}
                    onChange={(e) =>
                      updateAction(
                        index,
                        "timeout",
                        parseInt(e.target.value),
                      )
                    }
                    className="mt-1"
                    min="1"
                    max="300"
                  />
                </div>
              </div>
              {action.dryRun && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <p className="text-sm text-amber-800 font-medium">
                    Dry Run Result
                  </p>
                  <p className="text-xs text-amber-700 mt-1 font-mono">
                    Would execute: {action.verb} on 5 devices via{" "}
                    {action.integration}
                  </p>
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => removeAction(index)}
              className="text-slate-400 hover:text-red-600"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export function PolicyEditor({
  open,
  onOpenChange,
}: PolicyEditorProps) {
  const [policyData, setPolicyData] = useState({
    name: "Smart Plug Control",
    description:
      "Automatically shutdown non-critical devices when UPS battery drops below 20%",
    enabled: true,
    triggerType: "ups.battery",
    conditionOperator: "<=",
    conditionValue: "20",
    conditionUnit: "%",
    suppressionDuration: "5",
    suppressionUnit: "minutes",
    targetTypes: ["Host"],
    labelFilters: "tier=low",
    previewCount: 5,
  });

  const [actions, setActions] = useState<Action[]>([
    {
      id: "1",
      integration: "tapo",
      capability: "power.control",
      verb: "shutdown",
      concurrency: 5,
      backoff: 1000,
      timeout: 30,
      dryRun: false,
    },
  ]);

  const [validationStatus, setValidationStatus] = useState<
    "valid" | "invalid" | "pending"
  >("valid");
  const [showJsonPreview, setShowJsonPreview] = useState(false);

  const generateJsonPreview = () => {
    return {
      name: policyData.name,
      description: policyData.description,
      enabled: policyData.enabled,
      trigger: {
        type: policyData.triggerType,
        condition: `${policyData.conditionOperator} ${policyData.conditionValue}${policyData.conditionUnit}`,
        suppression: {
          duration: `${policyData.suppressionDuration} ${policyData.suppressionUnit}`,
        },
      },
      targets: {
        types: policyData.targetTypes,
        filters: policyData.labelFilters,
      },
      actions: actions.map((action) => ({
        integration: action.integration,
        capability: action.capability,
        verb: action.verb,
        options: {
          concurrency: action.concurrency,
          backoff: action.backoff,
          timeout: action.timeout,
        },
        dryRun: action.dryRun,
      })),
    };
  };

  const moveAction = (
    dragIndex: number,
    hoverIndex: number,
  ) => {
    const draggedAction = actions[dragIndex];
    const newActions = [...actions];
    newActions.splice(dragIndex, 1);
    newActions.splice(hoverIndex, 0, draggedAction);
    setActions(newActions);
  };

  const updateAction = (
    index: number,
    field: keyof Action,
    value: any,
  ) => {
    const newActions = [...actions];
    newActions[index] = {
      ...newActions[index],
      [field]: value,
    };
    setActions(newActions);
  };

  const removeAction = (index: number) => {
    const newActions = actions.filter((_, i) => i !== index);
    setActions(newActions);
  };

  const addAction = () => {
    const newAction: Action = {
      id: Date.now().toString(),
      integration: "",
      capability: "",
      verb: "",
      concurrency: 1,
      backoff: 1000,
      timeout: 30,
      dryRun: false,
    };
    setActions([...actions, newAction]);
  };

  const handleSave = () => {
    console.log("Saving policy:", { policyData, actions });
    onOpenChange(false);
  };

  const handleDryRun = () => {
    console.log("Running dry run for policy:", {
      policyData,
      actions,
    });
  };

  return (
    <DndProvider backend={HTML5Backend}>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="w-full sm:w-[40%] min-w-[600px] max-w-[800px] p-0 flex flex-col h-full"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>
              {policyData.name
                ? `Edit Policy: ${policyData.name}`
                : "New Policy"}
            </SheetTitle>
            <SheetDescription>
              Configure triggers, targets, and actions for your policy
            </SheetDescription>
          </SheetHeader>

          {/* Header */}
          <div className="shrink-0 border-b border-slate-200 bg-white p-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Zap className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    {policyData.name
                      ? `Edit Policy: ${policyData.name}`
                      : "New Policy"}
                  </h2>
                  <p className="text-sm text-slate-600">
                    Configure triggers, targets, and actions
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onOpenChange(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
          </div>

          {/* Body - ScrollArea with proper height constraints */}
          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full px-6">
              <div className="space-y-6 py-6">
                {/* Basics Section */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-base font-semibold text-slate-900">
                      Basics
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label
                        htmlFor="policy-name"
                        className="text-sm font-medium text-slate-700"
                      >
                        Policy Name{" "}
                        <span className="text-red-500">*</span>
                      </Label>
                      <Input
                        id="policy-name"
                        value={policyData.name}
                        onChange={(e) =>
                          setPolicyData({
                            ...policyData,
                            name: e.target.value,
                          })
                        }
                        placeholder="Enter policy name"
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label
                        htmlFor="policy-description"
                        className="text-sm font-medium text-slate-700"
                      >
                        Description
                      </Label>
                      <Textarea
                        id="policy-description"
                        value={policyData.description}
                        onChange={(e) =>
                          setPolicyData({
                            ...policyData,
                            description: e.target.value,
                          })
                        }
                        placeholder="Enter policy description"
                        rows={3}
                        className="mt-1"
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label
                        htmlFor="policy-enabled"
                        className="text-sm font-medium text-slate-700"
                      >
                        Enable Policy
                      </Label>
                      <Switch
                        id="policy-enabled"
                        checked={policyData.enabled}
                        onCheckedChange={(checked) =>
                          setPolicyData({
                            ...policyData,
                            enabled: checked,
                          })
                        }
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Trigger Section */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-base font-semibold text-slate-900">
                      Trigger
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label className="text-sm font-medium text-slate-700">
                        Trigger Type
                      </Label>
                      <Select
                        value={policyData.triggerType}
                        onValueChange={(value) =>
                          setPolicyData({
                            ...policyData,
                            triggerType: value,
                          })
                        }
                      >
                        <SelectTrigger className="mt-1">
                          <SelectValue placeholder="Select trigger type" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ups.status">
                            UPS Status
                          </SelectItem>
                          <SelectItem value="ups.battery">
                            Battery Percentage
                          </SelectItem>
                          <SelectItem value="ups.runtime">
                            Runtime Remaining
                          </SelectItem>
                          <SelectItem value="manual">
                            Manual
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-slate-700">
                        Condition
                      </Label>
                      <div className="flex gap-2 mt-1">
                        <Select
                          value={policyData.conditionOperator}
                          onValueChange={(value) =>
                            setPolicyData({
                              ...policyData,
                              conditionOperator: value,
                            })
                          }
                        >
                          <SelectTrigger className="w-20">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="<=">≤</SelectItem>
                            <SelectItem value=">=">≥</SelectItem>
                            <SelectItem value="==">==</SelectItem>
                            <SelectItem value="!=">!=</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input
                          value={policyData.conditionValue}
                          onChange={(e) =>
                            setPolicyData({
                              ...policyData,
                              conditionValue: e.target.value,
                            })
                          }
                          placeholder="Value"
                          className="flex-1"
                        />
                        <Select
                          value={policyData.conditionUnit}
                          onValueChange={(value) =>
                            setPolicyData({
                              ...policyData,
                              conditionUnit: value,
                            })
                          }
                        >
                          <SelectTrigger className="w-20">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="%">%</SelectItem>
                            <SelectItem value="min">
                              min
                            </SelectItem>
                            <SelectItem value="sec">
                              sec
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-slate-700">
                        Suppression Window
                      </Label>
                      <div className="flex gap-2 mt-1">
                        <Input
                          value={policyData.suppressionDuration}
                          onChange={(e) =>
                            setPolicyData({
                              ...policyData,
                              suppressionDuration: e.target.value,
                            })
                          }
                          placeholder="Duration"
                          className="flex-1"
                        />
                        <Select
                          value={policyData.suppressionUnit}
                          onValueChange={(value) =>
                            setPolicyData({
                              ...policyData,
                              suppressionUnit: value,
                            })
                          }
                        >
                          <SelectTrigger className="w-32">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="minutes">
                              minutes
                            </SelectItem>
                            <SelectItem value="hours">
                              hours
                            </SelectItem>
                            <SelectItem value="days">
                              days
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Targets Section */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-base font-semibold text-slate-900">
                      Targets
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label className="text-sm font-medium text-slate-700">
                        Target Types
                      </Label>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {policyData.targetTypes.map((type) => (
                          <Badge
                            key={type}
                            variant="secondary"
                            className="bg-blue-50 text-blue-700 hover:bg-blue-100"
                          >
                            {type}
                            <X
                              className="ml-1 h-3 w-3 cursor-pointer"
                              onClick={() => {
                                const newTypes =
                                  policyData.targetTypes.filter(
                                    (t) => t !== type,
                                  );
                                setPolicyData({
                                  ...policyData,
                                  targetTypes: newTypes,
                                });
                              }}
                            />
                          </Badge>
                        ))}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2 text-xs"
                          onClick={() => {
                            const availableTypes = [
                              "VM",
                              "Host",
                              "PoE Port",
                              "Smart Plug",
                            ];
                            const newType = availableTypes.find(
                              (t) =>
                                !policyData.targetTypes.includes(
                                  t,
                                ),
                            );
                            if (newType) {
                              setPolicyData({
                                ...policyData,
                                targetTypes: [
                                  ...policyData.targetTypes,
                                  newType,
                                ],
                              });
                            }
                          }}
                        >
                          <Plus className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                    <div>
                      <Label
                        htmlFor="label-filters"
                        className="text-sm font-medium text-slate-700"
                      >
                        Label Filters
                      </Label>
                      <Input
                        id="label-filters"
                        value={policyData.labelFilters}
                        onChange={(e) =>
                          setPolicyData({
                            ...policyData,
                            labelFilters: e.target.value,
                          })
                        }
                        placeholder="key:value, env:prod"
                        className="mt-1 font-mono text-sm"
                      />
                    </div>
                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-slate-600">
                          Matched targets:
                        </span>
                        <Badge
                          variant="outline"
                          className="bg-white"
                        >
                          {policyData.previewCount} devices
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-sm text-blue-600 hover:text-blue-700"
                      >
                        Preview targets
                        <ExternalLink className="ml-1 h-3 w-3" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Actions Section */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-4">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base font-semibold text-slate-900">
                        Actions
                      </CardTitle>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={addAction}
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        Add Action
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {actions.map((action, index) => (
                      <ActionItem
                        key={action.id}
                        action={action}
                        index={index}
                        moveAction={moveAction}
                        updateAction={updateAction}
                        removeAction={removeAction}
                      />
                    ))}
                  </CardContent>
                </Card>
              </div>
            </ScrollArea>
          </div>

          {/* JSON Preview */}
          <Collapsible
            open={showJsonPreview}
            onOpenChange={setShowJsonPreview}
            className="shrink-0"
          >
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                className="w-full justify-between p-4 border-t border-slate-200 rounded-none"
              >
                <span className="text-sm font-medium">
                  JSON Preview
                </span>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${showJsonPreview ? "rotate-180" : ""}`}
                />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t border-slate-200">
              <div className="p-4 bg-slate-900 text-green-400 max-h-48 overflow-y-auto">
                <pre className="text-xs font-mono">
                  {JSON.stringify(
                    generateJsonPreview(),
                    null,
                    2,
                  )}
                </pre>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Footer */}
          <div className="shrink-0 border-t border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {validationStatus === "valid" && (
                  <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Valid
                  </Badge>
                )}
                {validationStatus === "invalid" && (
                  <Badge variant="destructive">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    Needs Review
                  </Badge>
                )}
                {validationStatus === "pending" && (
                  <Badge variant="secondary">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    Validating...
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="outline"
                  onClick={handleDryRun}
                >
                  Dry Run Policy
                </Button>
                <Button
                  onClick={handleSave}
                  disabled={validationStatus === "invalid"}
                >
                  Save Policy
                </Button>
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </DndProvider>
  );
}