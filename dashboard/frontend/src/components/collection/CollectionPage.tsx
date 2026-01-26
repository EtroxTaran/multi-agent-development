/**
 * Collection Page - Browse and manage rules, skills, and templates
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Wrench,
  FileCode,
  Search,
  Filter,
  RefreshCw,
  Eye,
  Tags,
  CheckCircle2,
  AlertCircle,
  Plus,
  Pencil,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { CollectionFormDialog, DeleteItemDialog } from "./CollectionFormDialog";

// Note: fetchItem returns full item with content for viewing

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

interface SyncResult {
  items_added: number;
  items_updated: number;
  items_removed: number;
  errors: string[];
}

interface TagsList {
  technology: string[];
  feature: string[];
  priority: string[];
}

const API_BASE = "/api/collection";

// API Functions
async function fetchItems(filters: {
  type?: string;
  technologies?: string;
  priority?: string;
}): Promise<CollectionItem[]> {
  const params = new URLSearchParams();
  if (filters.type && filters.type !== "all")
    params.set("item_type", filters.type);
  if (filters.technologies) params.set("technologies", filters.technologies);
  if (filters.priority && filters.priority !== "all")
    params.set("priority", filters.priority);
  params.set("include_content", "false");

  const res = await fetch(`${API_BASE}/items?${params}`);
  if (!res.ok) throw new Error("Failed to fetch items");
  return res.json();
}

async function fetchItem(itemId: string): Promise<CollectionItem> {
  const res = await fetch(`${API_BASE}/items/${itemId}`);
  if (!res.ok) throw new Error("Failed to fetch item");
  return res.json();
}

async function fetchTags(): Promise<TagsList> {
  const res = await fetch(`${API_BASE}/tags`);
  if (!res.ok) throw new Error("Failed to fetch tags");
  return res.json();
}

async function syncCollection(): Promise<SyncResult> {
  const res = await fetch(`${API_BASE}/sync`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to sync");
  return res.json();
}

// Icon for item type
function ItemTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "rule":
      return <BookOpen className="h-4 w-4" />;
    case "skill":
      return <Wrench className="h-4 w-4" />;
    case "template":
      return <FileCode className="h-4 w-4" />;
    default:
      return <FileCode className="h-4 w-4" />;
  }
}

// Priority badge color
function getPriorityColor(priority: string): string {
  switch (priority) {
    case "critical":
      return "bg-red-500/20 text-red-400 border-red-500/30";
    case "high":
      return "bg-orange-500/20 text-orange-400 border-orange-500/30";
    case "medium":
      return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    case "low":
      return "bg-gray-500/20 text-gray-400 border-gray-500/30";
    default:
      return "bg-gray-500/20 text-gray-400 border-gray-500/30";
  }
}

// Item Card Component
function CollectionItemCard({
  item,
  onView,
  onEdit,
  onDelete,
}: {
  item: CollectionItem;
  onView: (id: string) => void;
  onEdit: (item: CollectionItem) => void;
  onDelete: (item: CollectionItem) => void;
}) {
  return (
    <Card className="bg-card/50 border-border/50 hover:border-primary/50 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <ItemTypeIcon type={item.item_type} />
            </div>
            <div>
              <CardTitle className="text-sm font-medium">{item.name}</CardTitle>
              <CardDescription className="text-xs">
                {item.category}
              </CardDescription>
            </div>
          </div>
          <Badge
            variant="outline"
            className={getPriorityColor(item.tags.priority)}
          >
            {item.tags.priority}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-xs text-muted-foreground line-clamp-2 mb-3">
          {item.summary || "No description available"}
        </p>

        {/* Technology tags */}
        <div className="flex flex-wrap gap-1 mb-3">
          {item.tags.technology.slice(0, 3).map((tech) => (
            <Badge
              key={tech}
              variant="secondary"
              className="text-xs px-1.5 py-0"
            >
              {tech}
            </Badge>
          ))}
          {item.tags.technology.length > 3 && (
            <Badge variant="secondary" className="text-xs px-1.5 py-0">
              +{item.tags.technology.length - 3}
            </Badge>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            onClick={() => onView(item.id)}
          >
            <Eye className="h-3 w-3 mr-1" />
            View
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs px-2"
            onClick={() => onEdit(item)}
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs px-2 hover:bg-destructive/20 hover:text-destructive"
            onClick={() => onDelete(item)}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Item Detail Dialog
function ItemDetailDialog({
  itemId,
  open,
  onOpenChange,
}: {
  itemId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: item, isLoading } = useQuery({
    queryKey: ["collection-item", itemId],
    queryFn: () => fetchItem(itemId!),
    enabled: !!itemId && open,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : item ? (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <ItemTypeIcon type={item.item_type} />
                <DialogTitle>{item.name}</DialogTitle>
              </div>
              <DialogDescription>
                {item.category} • Version {item.version}
              </DialogDescription>
            </DialogHeader>

            {/* Tags */}
            <div className="flex flex-wrap gap-2 py-2">
              <Badge
                variant="outline"
                className={getPriorityColor(item.tags.priority)}
              >
                {item.tags.priority}
              </Badge>
              {item.tags.technology.map((tech) => (
                <Badge key={tech} variant="secondary">
                  {tech}
                </Badge>
              ))}
              {item.tags.feature.map((feat) => (
                <Badge key={feat} variant="outline">
                  {feat}
                </Badge>
              ))}
            </div>

            {/* Summary */}
            <p className="text-sm text-muted-foreground">{item.summary}</p>

            {/* Content */}
            <div className="flex-1 overflow-auto mt-4 rounded-lg bg-muted/50 p-4">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {item.content}
              </pre>
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            Item not found
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Main Collection Page
export function CollectionPage() {
  const queryClient = useQueryClient();

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [technologyFilter, setTechnologyFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Detail dialog
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Create/Edit/Delete dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [itemToEdit, setItemToEdit] = useState<CollectionItem | null>(null);
  const [itemToDelete, setItemToDelete] = useState<CollectionItem | null>(null);

  // Fetch items
  const { data: items = [], isLoading } = useQuery({
    queryKey: [
      "collection-items",
      typeFilter,
      technologyFilter,
      priorityFilter,
    ],
    queryFn: () =>
      fetchItems({
        type: typeFilter,
        technologies: technologyFilter,
        priority: priorityFilter,
      }),
  });

  // Fetch tags
  const { data: tags } = useQuery({
    queryKey: ["collection-tags"],
    queryFn: fetchTags,
  });

  // Sync mutation
  const syncMutation = useMutation({
    mutationFn: syncCollection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      queryClient.invalidateQueries({ queryKey: ["collection-tags"] });
    },
  });

  // Filter items by search query
  const filteredItems = items.filter(
    (item) =>
      item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.summary.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  // Group items by type
  const ruleItems = filteredItems.filter((i) => i.item_type === "rule");
  const skillItems = filteredItems.filter((i) => i.item_type === "skill");
  const templateItems = filteredItems.filter((i) => i.item_type === "template");

  const handleViewItem = (id: string) => {
    setSelectedItem(id);
    setDetailOpen(true);
  };

  const handleEditItem = (item: CollectionItem) => {
    setItemToEdit(item);
    setEditDialogOpen(true);
  };

  const handleDeleteItem = (item: CollectionItem) => {
    setItemToDelete(item);
    setDeleteDialogOpen(true);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Collection</h1>
          <p className="text-muted-foreground">
            Browse and manage rules, skills, and templates
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create
          </Button>
          <Button
            variant="outline"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${
                syncMutation.isPending ? "animate-spin" : ""
              }`}
            />
            Sync
          </Button>
        </div>
      </div>

      {/* Sync result message */}
      {syncMutation.isSuccess && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/30">
          <CheckCircle2 className="h-4 w-4 text-green-500" />
          <span className="text-sm">
            Synced: {syncMutation.data.items_added} added,{" "}
            {syncMutation.data.items_updated} updated,{" "}
            {syncMutation.data.items_removed} removed
          </span>
        </div>
      )}

      {syncMutation.isError && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
          <AlertCircle className="h-4 w-4 text-red-500" />
          <span className="text-sm text-red-400">
            Sync failed. Check backend logs.
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search items..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[140px]">
            <Filter className="h-4 w-4 mr-2" />
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="rule">Rules</SelectItem>
            <SelectItem value="skill">Skills</SelectItem>
            <SelectItem value="template">Templates</SelectItem>
          </SelectContent>
        </Select>

        <Select value={priorityFilter} onValueChange={setPriorityFilter}>
          <SelectTrigger className="w-[140px]">
            <Tags className="h-4 w-4 mr-2" />
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Priorities</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        {tags?.technology && tags.technology.length > 0 && (
          <Select
            value={technologyFilter || "all-tech"}
            onValueChange={(v) =>
              setTechnologyFilter(v === "all-tech" ? "" : v)
            }
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Technology" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-tech">All Technologies</SelectItem>
              {tags.technology.map((tech) => (
                <SelectItem key={tech} value={tech}>
                  {tech}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-blue-500/10 border-blue-500/30">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Rules</p>
              <p className="text-2xl font-bold">{ruleItems.length}</p>
            </div>
            <BookOpen className="h-8 w-8 text-blue-500/50" />
          </CardContent>
        </Card>
        <Card className="bg-green-500/10 border-green-500/30">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Skills</p>
              <p className="text-2xl font-bold">{skillItems.length}</p>
            </div>
            <Wrench className="h-8 w-8 text-green-500/50" />
          </CardContent>
        </Card>
        <Card className="bg-purple-500/10 border-purple-500/30">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Templates</p>
              <p className="text-2xl font-bold">{templateItems.length}</p>
            </div>
            <FileCode className="h-8 w-8 text-purple-500/50" />
          </CardContent>
        </Card>
      </div>

      {/* Loading state */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <FileCode className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>No items found</p>
          <p className="text-sm">
            Try adjusting your filters or sync the collection
          </p>
        </div>
      ) : (
        <>
          {/* Rules Section */}
          {ruleItems.length > 0 &&
            (typeFilter === "all" || typeFilter === "rule") && (
              <section>
                <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-blue-500" />
                  Rules ({ruleItems.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {ruleItems.map((item) => (
                    <CollectionItemCard
                      key={item.id}
                      item={item}
                      onView={handleViewItem}
                      onEdit={handleEditItem}
                      onDelete={handleDeleteItem}
                    />
                  ))}
                </div>
              </section>
            )}

          {/* Skills Section */}
          {skillItems.length > 0 &&
            (typeFilter === "all" || typeFilter === "skill") && (
              <section>
                <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                  <Wrench className="h-5 w-5 text-green-500" />
                  Skills ({skillItems.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {skillItems.map((item) => (
                    <CollectionItemCard
                      key={item.id}
                      item={item}
                      onView={handleViewItem}
                      onEdit={handleEditItem}
                      onDelete={handleDeleteItem}
                    />
                  ))}
                </div>
              </section>
            )}

          {/* Templates Section */}
          {templateItems.length > 0 &&
            (typeFilter === "all" || typeFilter === "template") && (
              <section>
                <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                  <FileCode className="h-5 w-5 text-purple-500" />
                  Templates ({templateItems.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {templateItems.map((item) => (
                    <CollectionItemCard
                      key={item.id}
                      item={item}
                      onView={handleViewItem}
                      onEdit={handleEditItem}
                      onDelete={handleDeleteItem}
                    />
                  ))}
                </div>
              </section>
            )}
        </>
      )}

      {/* Item Detail Dialog */}
      <ItemDetailDialog
        itemId={selectedItem}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      {/* Create Dialog */}
      <CollectionFormDialog
        mode="create"
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />

      {/* Edit Dialog */}
      <CollectionFormDialog
        mode="edit"
        item={itemToEdit}
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) setItemToEdit(null);
        }}
      />

      {/* Delete Dialog */}
      <DeleteItemDialog
        item={itemToDelete}
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open);
          if (!open) setItemToDelete(null);
        }}
      />
    </div>
  );
}
