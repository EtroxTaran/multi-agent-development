/**
 * Collection Item Form Dialog - Create/Edit collection items
 */

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface CollectionTags {
  technology: string[];
  feature: string[];
  priority: string;
}

interface CollectionItem {
  id: string;
  name: string;
  item_type: string;
  category: string;
  file_path: string;
  summary: string;
  tags: CollectionTags;
  version: number;
  is_active: boolean;
  content?: string;
}

interface FormData {
  name: string;
  item_type: string;
  category: string;
  content: string;
  summary: string;
  tags: CollectionTags;
}

const API_BASE = "/api/collection";

// API Functions
async function createItem(data: FormData): Promise<CollectionItem> {
  const res = await fetch(`${API_BASE}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ detail: "Failed to create item" }));
    throw new Error(error.detail || "Failed to create item");
  }
  return res.json();
}

async function updateItem(
  itemId: string,
  data: Partial<FormData>,
): Promise<CollectionItem> {
  const res = await fetch(`${API_BASE}/items/${itemId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ detail: "Failed to update item" }));
    throw new Error(error.detail || "Failed to update item");
  }
  return res.json();
}

async function deleteItem(
  itemId: string,
  hard: boolean = false,
): Promise<void> {
  const res = await fetch(`${API_BASE}/items/${itemId}?hard=${hard}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ detail: "Failed to delete item" }));
    throw new Error(error.detail || "Failed to delete item");
  }
}

// Category options by type
const CATEGORIES = {
  rule: ["guardrails", "coding-standards", "references", "workflows"],
  skill: [
    "orchestrate",
    "implement",
    "validate",
    "verify",
    "test-writer",
    "discover",
    "plan",
    "resolve-conflict",
  ],
  template: ["claude-md", "gemini-md", "react-frontend", "python-backend"],
};

const PRIORITIES = ["critical", "high", "medium", "low"];

interface CollectionFormDialogProps {
  mode: "create" | "edit";
  item?: CollectionItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CollectionFormDialog({
  mode,
  item,
  open,
  onOpenChange,
}: CollectionFormDialogProps) {
  const queryClient = useQueryClient();

  // Form state
  const [formData, setFormData] = useState<FormData>({
    name: "",
    item_type: "rule",
    category: "guardrails",
    content: "",
    summary: "",
    tags: {
      technology: [],
      feature: [],
      priority: "medium",
    },
  });

  // Tag input state
  const [techInput, setTechInput] = useState("");
  const [featureInput, setFeatureInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Initialize form with item data when editing
  useEffect(() => {
    if (mode === "edit" && item) {
      setFormData({
        name: item.name,
        item_type: item.item_type,
        category: item.category,
        content: item.content || "",
        summary: item.summary,
        tags: {
          technology: [...item.tags.technology],
          feature: [...item.tags.feature],
          priority: item.tags.priority,
        },
      });
    } else if (mode === "create") {
      // Reset form for create
      setFormData({
        name: "",
        item_type: "rule",
        category: "guardrails",
        content: "",
        summary: "",
        tags: {
          technology: [],
          feature: [],
          priority: "medium",
        },
      });
    }
    setError(null);
  }, [mode, item, open]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: createItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      queryClient.invalidateQueries({ queryKey: ["collection-tags"] });
      onOpenChange(false);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: Partial<FormData>) => updateItem(item!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      queryClient.invalidateQueries({
        queryKey: ["collection-item", item?.id],
      });
      onOpenChange(false);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  // Handle form submission
  const handleSubmit = () => {
    setError(null);

    // Validation
    if (!formData.name.trim()) {
      setError("Name is required");
      return;
    }
    if (!formData.content.trim()) {
      setError("Content is required");
      return;
    }

    if (mode === "create") {
      createMutation.mutate(formData);
    } else if (mode === "edit" && item) {
      // Only send changed fields for update
      updateMutation.mutate({
        content: formData.content,
        summary: formData.summary,
        tags: formData.tags,
      });
    }
  };

  // Handle tag addition
  const addTag = (type: "technology" | "feature", value: string) => {
    const trimmed = value.trim().toLowerCase();
    if (trimmed && !formData.tags[type].includes(trimmed)) {
      setFormData({
        ...formData,
        tags: {
          ...formData.tags,
          [type]: [...formData.tags[type], trimmed],
        },
      });
    }
    if (type === "technology") setTechInput("");
    else setFeatureInput("");
  };

  // Handle tag removal
  const removeTag = (type: "technology" | "feature", value: string) => {
    setFormData({
      ...formData,
      tags: {
        ...formData.tags,
        [type]: formData.tags[type].filter((t) => t !== value),
      },
    });
  };

  // Get categories for current type
  const categories =
    CATEGORIES[formData.item_type as keyof typeof CATEGORIES] ||
    CATEGORIES.rule;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Create New Item" : `Edit: ${item?.name}`}
          </DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "Add a new rule, skill, or template to the collection"
              : "Update the item content, summary, or tags"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error message */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              <X className="h-4 w-4" />
              {error}
            </div>
          )}

          {/* Name (only for create) */}
          {mode === "create" && (
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                placeholder="e.g., security-best-practices"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
              />
            </div>
          )}

          {/* Type and Category (only for create) */}
          {mode === "create" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Type *</Label>
                <Select
                  value={formData.item_type}
                  onValueChange={(v) =>
                    setFormData({
                      ...formData,
                      item_type: v,
                      category:
                        CATEGORIES[v as keyof typeof CATEGORIES]?.[0] ||
                        "guardrails",
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rule">Rule</SelectItem>
                    <SelectItem value="skill">Skill</SelectItem>
                    <SelectItem value="template">Template</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Category *</Label>
                <Select
                  value={formData.category}
                  onValueChange={(v) =>
                    setFormData({ ...formData, category: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* Summary */}
          <div className="space-y-2">
            <Label htmlFor="summary">Summary</Label>
            <Input
              id="summary"
              placeholder="Brief description of this item"
              value={formData.summary}
              onChange={(e) =>
                setFormData({ ...formData, summary: e.target.value })
              }
            />
          </div>

          {/* Content */}
          <div className="space-y-2">
            <Label htmlFor="content">Content *</Label>
            <Textarea
              id="content"
              placeholder="Enter the rule, skill, or template content..."
              className="min-h-[200px] font-mono text-sm"
              value={formData.content}
              onChange={(e) =>
                setFormData({ ...formData, content: e.target.value })
              }
            />
          </div>

          {/* Priority */}
          <div className="space-y-2">
            <Label>Priority</Label>
            <Select
              value={formData.tags.priority}
              onValueChange={(v) =>
                setFormData({
                  ...formData,
                  tags: { ...formData.tags, priority: v },
                })
              }
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITIES.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Technology Tags */}
          <div className="space-y-2">
            <Label>Technology Tags</Label>
            <div className="flex gap-2">
              <Input
                placeholder="Add technology (press Enter)"
                value={techInput}
                onChange={(e) => setTechInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTag("technology", techInput);
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => addTag("technology", techInput)}
              >
                Add
              </Button>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {formData.tags.technology.map((tag) => (
                <Badge
                  key={tag}
                  variant="secondary"
                  className="cursor-pointer hover:bg-destructive/20"
                  onClick={() => removeTag("technology", tag)}
                >
                  {tag} ×
                </Badge>
              ))}
            </div>
          </div>

          {/* Feature Tags */}
          <div className="space-y-2">
            <Label>Feature Tags</Label>
            <div className="flex gap-2">
              <Input
                placeholder="Add feature (press Enter)"
                value={featureInput}
                onChange={(e) => setFeatureInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTag("feature", featureInput);
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => addTag("feature", featureInput)}
              >
                Add
              </Button>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {formData.tags.feature.map((tag) => (
                <Badge
                  key={tag}
                  variant="outline"
                  className="cursor-pointer hover:bg-destructive/20"
                  onClick={() => removeTag("feature", tag)}
                >
                  {tag} ×
                </Badge>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                {mode === "create" ? "Creating..." : "Saving..."}
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {mode === "create" ? "Create Item" : "Save Changes"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Delete Confirmation Dialog
interface DeleteDialogProps {
  item: CollectionItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteItemDialog({
  item,
  open,
  onOpenChange,
}: DeleteDialogProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: () => deleteItem(item!.id, false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      onOpenChange(false);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Delete Item</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete "{item?.name}"? This action will
            mark the item as inactive.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            <X className="h-4 w-4" />
            {error}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={deleteMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Deleting...
              </>
            ) : (
              "Delete"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
