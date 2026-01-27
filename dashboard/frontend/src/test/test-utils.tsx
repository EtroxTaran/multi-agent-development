/**
 * Test utilities with React Query and Router wrappers
 */

import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
  createRootRoute,
  createRoute,
} from "@tanstack/react-router";

/**
 * Create a test QueryClient with disabled retries and caching
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/**
 * Wrapper component for tests that need React Query
 */
interface WrapperProps {
  children: React.ReactNode;
}

function createWrapper(queryClient?: QueryClient) {
  const client = queryClient ?? createTestQueryClient();
  return function Wrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

/**
 * Custom render with React Query provider
 */
interface CustomRenderOptions extends Omit<RenderOptions, "wrapper"> {
  queryClient?: QueryClient;
}

export function renderWithQuery(
  ui: ReactElement,
  options: CustomRenderOptions = {},
) {
  const { queryClient, ...renderOptions } = options;
  const Wrapper = createWrapper(queryClient);

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient: queryClient ?? createTestQueryClient(),
  };
}

/**
 * Create a test router for route testing
 */
export function createTestRouter(
  element: ReactElement,
  initialPath: string = "/",
) {
  const rootRoute = createRootRoute({
    component: () => element,
  });

  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => element,
  });

  const routeTree = rootRoute.addChildren([indexRoute]);

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });

  return router;
}

/**
 * Render with both React Query and Router
 */
export function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions & { initialPath?: string } = {},
) {
  const { queryClient, initialPath = "/", ...renderOptions } = options;
  const client = queryClient ?? createTestQueryClient();

  const rootRoute = createRootRoute({
    component: () => (
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    ),
  });

  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => null,
  });

  const projectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/projects/$projectName",
    component: () => null,
  });

  const routeTree = rootRoute.addChildren([indexRoute, projectRoute]);

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });

  return {
    ...render(<RouterProvider router={router} />, renderOptions),
    queryClient: client,
    router,
  };
}

/**
 * Wait for queries to settle
 */
export async function waitForQueries(queryClient: QueryClient) {
  await queryClient.isFetching();
}

// Re-export testing library utilities
// eslint-disable-next-line react-refresh/only-export-components -- test utility re-exports
export * from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
