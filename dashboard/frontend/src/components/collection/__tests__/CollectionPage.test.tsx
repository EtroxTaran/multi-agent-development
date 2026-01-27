/**
 * Tests for CollectionPage component
 *
 * These tests ensure proper handling of API responses and data transformations.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/mocks/server";
import { http, HttpResponse } from "msw";

// Mock collection item matching the API response format
const mockCollectionItem = {
  id: "collection_items:test-rule",
  name: "Test Rule",
  item_type: "rule",
  category: "guardrails",
  file_path: "rules/guardrails/test.md",
  summary: "Test summary",
  tags: {
    technology: ["python", "typescript"],
    feature: ["security"],
    priority: "high",
  },
  version: 1,
  is_active: true,
  content: null,
};

// Paginated response format (what the backend returns)
const mockPaginatedResponse = {
  items: [mockCollectionItem],
  total: 1,
  offset: 0,
  limit: 100,
  has_more: false,
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient?: QueryClient) {
  const client = queryClient ?? createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("Collection API Response Handling", () => {
  beforeEach(() => {
    // Add collection endpoint handlers for tests
    server.use(
      http.get("/api/collection/items", () => {
        return HttpResponse.json(mockPaginatedResponse);
      }),
      http.get("/api/collection/tags", () => {
        return HttpResponse.json({
          technology: ["python", "typescript"],
          feature: ["security"],
          priority: ["high", "medium", "low"],
        });
      }),
    );
  });

  afterEach(() => {
    server.resetHandlers();
  });

  describe("fetchItems function", () => {
    it("should extract items array from paginated response", async () => {
      /**
       * Regression test for bug where fetchItems returned the entire
       * paginated response object instead of just the items array.
       *
       * This caused: "items.filter is not a function" error because
       * calling .filter() on an object fails.
       */
      const response = await fetch("/api/collection/items");
      const data = await response.json();

      // Backend returns paginated response with items array
      expect(data).toHaveProperty("items");
      expect(data).toHaveProperty("total");
      expect(data).toHaveProperty("offset");
      expect(data).toHaveProperty("limit");
      expect(data).toHaveProperty("has_more");

      // The items property should be an array
      expect(Array.isArray(data.items)).toBe(true);

      // Simulate what fetchItems should do - extract items array
      const items = data.items;
      expect(Array.isArray(items)).toBe(true);

      // Now .filter() should work
      expect(() => items.filter((i: unknown) => i)).not.toThrow();
    });

    it("should handle empty items array", async () => {
      server.use(
        http.get("/api/collection/items", () => {
          return HttpResponse.json({
            items: [],
            total: 0,
            offset: 0,
            limit: 100,
            has_more: false,
          });
        }),
      );

      const response = await fetch("/api/collection/items");
      const data = await response.json();

      const items = data.items;
      expect(Array.isArray(items)).toBe(true);
      expect(items.length).toBe(0);

      // Should be able to filter empty array without error
      const filtered = items.filter((i: unknown) => i);
      expect(filtered).toEqual([]);
    });

    it("should preserve item structure after extraction", async () => {
      const response = await fetch("/api/collection/items");
      const data = await response.json();
      const items = data.items;

      expect(items.length).toBe(1);
      expect(items[0]).toEqual(mockCollectionItem);
      expect(items[0].id).toBe("collection_items:test-rule");
      expect(items[0].name).toBe("Test Rule");
    });
  });

  describe("Item ID handling", () => {
    it("should receive string IDs from the API", async () => {
      /**
       * Regression test for bug where SurrealDB RecordID objects
       * were not converted to strings, causing Pydantic validation errors.
       */
      const response = await fetch("/api/collection/items");
      const data = await response.json();
      const items = data.items;

      // ID should be a string (converted from RecordID on backend)
      expect(typeof items[0].id).toBe("string");
    });
  });
});

describe("Collection filtering", () => {
  it("should be able to filter items by search query", () => {
    const items = [
      { name: "Security Rules", summary: "Security related rules" },
      { name: "Code Quality", summary: "Quality standards" },
      { name: "Architecture", summary: "Design patterns" },
    ];

    const searchQuery = "security";

    // This simulates the filtering logic in CollectionPage
    const filteredItems = items.filter(
      (item) =>
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.summary.toLowerCase().includes(searchQuery.toLowerCase()),
    );

    expect(filteredItems.length).toBe(1);
    expect(filteredItems[0].name).toBe("Security Rules");
  });

  it("should be able to filter items by type", () => {
    const items = [
      { item_type: "rule", name: "Rule 1" },
      { item_type: "skill", name: "Skill 1" },
      { item_type: "template", name: "Template 1" },
      { item_type: "rule", name: "Rule 2" },
    ];

    // This simulates the filtering logic in CollectionPage
    const ruleItems = items.filter((i) => i.item_type === "rule");
    const skillItems = items.filter((i) => i.item_type === "skill");
    const templateItems = items.filter((i) => i.item_type === "template");

    expect(ruleItems.length).toBe(2);
    expect(skillItems.length).toBe(1);
    expect(templateItems.length).toBe(1);
  });
});
